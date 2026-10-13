"""Offline tests: Gmail suggestions must never advance applications automatically."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gmail_responses as gmail


class GmailReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {"job_id": "jobs.cz:2001111111", "company": "Example Analytics s.r.o.", "title": "BI Reporting Analyst"},
            {"job_id": "prace.cz:2002222222", "company": "Acme Group", "title": "Junior Data Engineer"},
            {"job_id": "startupjobs.cz:44", "company": "NewCo", "title": "Marketing Analyst"},
        ]
        self.submitted = {"job:2001111111", "job:2002222222"}

    def email(self, subject="", sender="", snippet="", msg_id="m1", thread="t1"):
        return {
            "id": msg_id, "threadId": thread, "snippet": snippet,
            "payload": {"headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
            ]},
        }

    def test_opt_in_and_token_kept_in_keychain_only(self):
        fake_keyring = MagicMock()
        fake_keyring.get_password.return_value = None
        with patch.object(gmail, "_keyring", return_value=fake_keyring):
            self.assertFalse(gmail.is_connected())
            with self.assertRaisesRegex(RuntimeError, "подключите Gmail"):
                gmail._credentials()
            gmail.disconnect()
        fake_keyring.delete_password.assert_called_once_with(
            gmail.KEYRING_SERVICE, gmail.KEYRING_USER,
        )
        self.assertEqual(gmail.SCOPES, ("https://www.googleapis.com/auth/gmail.readonly",))

    def test_validate_only_desktop_oauth_json(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "client.json"
            entry = {
                "client_id": "local.apps.googleusercontent.com",
                "client_secret": "local",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            target.write_text(json.dumps({"installed": entry}))
            self.assertEqual(gmail.validate_client_file(target), str(target))
            target.write_text(json.dumps({"web": entry}))
            with self.assertRaises(ValueError):
                gmail.validate_client_file(target)
            target.write_text(json.dumps({"installed": {**entry, "token_uri": "https://evil.invalid/token"}}))
            with self.assertRaises(ValueError):
                gmail.validate_client_file(target)
            target.write_text("{bad")
            with self.assertRaises(ValueError):
                gmail.validate_client_file(target)

    def test_exact_job_id_only_for_confirmed_submission(self):
        mails = [
            self.email(subject="Re: Application 2001111111", msg_id="1", thread="t1"),
            self.email(subject="Position 2009999999", msg_id="2", thread="t2"),
            self.email(subject="Candidate 20022222220", msg_id="3", thread="t3"),
            self.email(subject="Marketing Analyst NewCo", msg_id="4", thread="t4"),
        ]
        rows = gmail.suggest_matches(mails, self.records, self.submitted)
        self.assertEqual([(r["job_id"], r["reason"]) for r in rows], [
            ("job:2001111111", "ID вакансии"),
        ])

    def test_company_and_title_required_to_avoid_false_positives(self):
        mails = [
            self.email(subject="Re: BI Reporting Analyst", sender="Team at Example Analytics s.r.o.", msg_id="a"),
            self.email(subject="BI Reporting Analyst", sender="newsletter@example.invalid", msg_id="b", thread="b"),
            self.email(subject="Example Analytics s.r.o. newsletter", msg_id="c", thread="c"),
            self.email(subject="Interview Junior Data Engineer", sender="Acme Group HR", msg_id="d", thread="d"),
        ]
        rows = gmail.suggest_matches(mails, self.records, self.submitted)
        self.assertEqual([r["message_id"] for r in rows], ["a", "d"])
        self.assertEqual(rows[0]["reason"], "Компания и название")

    def test_ambiguous_messages_are_not_assigned(self):
        row = self.email(
            subject="2001111111 and 2002222222", sender="HR team",
        )
        self.assertEqual(gmail.suggest_matches([row], self.records, self.submitted), [])
        # Only one suggestion per matching thread and application.
        mails = [
            self.email(subject="Application 2001111111", msg_id="1", thread="t"),
            self.email(subject="Re: 2001111111", msg_id="2", thread="t"),
        ]
        self.assertEqual(len(gmail.suggest_matches(mails, self.records, self.submitted)), 1)

    def test_does_not_mutate_supplied_records_or_stages(self):
        import copy
        before = copy.deepcopy(self.records)
        matched = gmail.suggest_matches(
            [self.email(subject="2001111111")],
            self.records, self.submitted,
        )
        self.assertEqual(self.records, before)
        self.assertEqual(len(matched), 1)
        self.assertNotIn("stage", matched[0])
        self.assertNotIn("notes", matched[0])

    def test_scans_readonly_headers_with_bounded_gmail_api(self):
        inbox_list = MagicMock()
        inbox_list.execute.return_value = {"messages": [
            {"id": "x"}, {"id": "y"},
        ]}
        first = self.email(subject="Application 2001111111", msg_id="x")
        second = self.email(subject="Hello", msg_id="y", thread="other")
        get_requests = [MagicMock(), MagicMock()]
        get_requests[0].execute.return_value = first
        get_requests[1].execute.return_value = second
        messages = MagicMock()
        messages.list.return_value = inbox_list
        messages.get.side_effect = get_requests
        service = MagicMock()
        service.users.return_value.messages.return_value = messages
        creds = object()
        with patch.object(gmail, "_credentials", return_value=creds), patch(
            "googleapiclient.discovery.build", return_value=service,
        ) as builder:
            candidates = gmail.scan(self.records, self.submitted, limit=1000)
        self.assertEqual([row["message_id"] for row in candidates], ["x"])
        builder.assert_called_once_with("gmail", "v1", credentials=creds, cache_discovery=False)
        messages.list.assert_called_once_with(
            userId="me", q="newer_than:90d -in:sent",
            maxResults=40, includeSpamTrash=False,
        )
        self.assertEqual(messages.get.call_count, 2)
        self.assertEqual(messages.get.call_args.kwargs["format"], "metadata")
        self.assertEqual(
            messages.get.call_args.kwargs["metadataHeaders"],
            ["From", "Subject", "Date"],
        )


if __name__ == "__main__":
    unittest.main()
