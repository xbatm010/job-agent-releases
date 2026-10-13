# Gmail read-only review (Job Agent Desktop 3.0.x)

**Opt-in only.** This macOS feature uses its own Google OAuth authorization.
Connecting Gmail to ChatGPT does not authorize the standalone Job Agent app.

## One-time personal Google Cloud setup

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create/select a project.
2. Enable **Gmail API** for that project.
3. In Google Auth Platform configure the OAuth consent screen (External for
   a personal Gmail account; add your own account under test users if in Testing).
4. Add **only** the scope `https://www.googleapis.com/auth/gmail.readonly`.
5. Create an OAuth client with **Application type: Desktop app**. Download its JSON
   to a private location on your Mac. Do not add it to GitHub, email it to us,
   or upload it into Job Agent releases.
6. In Job Agent → Settings → Gmail, choose that local Desktop OAuth JSON, then
   click **Подключить Gmail (только чтение)**. Finish Google's browser consent.
   Your browser may warn about an unverified test app if Google consent
   verification has not been completed.
7. Open Job Agent → Отклики → **Проверить ответы в Gmail**. Review suggested
   matches, open the email, and enter the employer's stage manually if correct.

## Privacy and limits

- Job Agent requests **gmail.readonly** only. It does not send, draft, delete,
  mark read, archive or label any messages.
- Gmail is queried **only by the user pressing the button**; no background
  polling, automatic reply, automatic stage update, or notification change.
- Each scan considers the **most recent 40 messages from 90 days** (excluding
  Sent, Spam and Trash); downloads only Subject/From/Date metadata and a short
  Gmail snippet, **not full email bodies or attachments**. Results are kept
  only in memory for the review dialog, not exported to public source,
  settings or the existing application history.
- Suggestions include conservative, unverified message-type hints (receipt, interview, rejection, result). Open the original message before confirming any status.\n- Suggestions require a unique posting ID or a unique company + role
  match among confirmed submissions. Ambiguous email matches are discarded.
  A missing suggestion is **not proof of no recruiter email**.
- OAuth tokens are kept in your local macOS Keychain using `keyring`.
  Job Agent settings retain only the selected **file path** (not its contents).
  Clicking Disconnect removes the locally stored OAuth tokens. You may
  separately revoke third-party access under your Google Account settings.
- Google OAuth Testing-mode refresh tokens may expire; reconnect if prompted.
  Distributing a shared public Gmail OAuth application with this scope may
  require Google verification and additional compliance reviews.

References:
- https://developers.google.com/workspace/gmail/api/quickstart/python
- https://developers.google.com/workspace/gmail/api/guides/list-messages
- https://developers.google.com/workspace/gmail/api/auth/scopes
