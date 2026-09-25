# Zoom cloud recording setup

This is a future operator checklist. The owner chose to configure Zoom access when implementation reaches import testing. No credentials are needed to maintain the specification.

## Account prerequisites

- The classes must be **cloud recordings** in the Zoom account authorizing the importer. Computer-only recordings use the local-file fallback.
- An account owner/admin, or a developer granted the required role permissions, must create and manage an internal Server-to-Server OAuth app. This app can access only its own Zoom account. If recordings instead belong to a separate account that cannot grant this access, revisit the authentication design with the owner.
- The recording host and account need cloud-recording eligibility. Zoom's cloud-recording audio transcript is available only when configured and currently supports English; mixed Bangla/English material still needs a real accuracy check.

## Owner/admin steps

1. In the Zoom web portal, confirm **Account Management → Account Settings → Recording & Transcript → Cloud recording** is enabled. Under Advanced cloud recording settings, enable **Create audio transcript** for future recordings if available.
2. In [Zoom App Marketplace](https://marketplace.zoom.us/), choose **Developer → Build App → Server-to-Server OAuth**. If Developer is absent, grant the account role permission to view/edit these apps and the recording scopes. Do not use a normal Zoom password as the application's integration credential.
3. Add the minimum read scopes needed for the chosen host: `cloud_recording:read:list_user_recordings:admin` and `cloud_recording:read:list_recording_files:admin`. Add `cloud_recording:read:meeting_transcript:admin` only if the transcript endpoint is used. Do not add recording write/delete scopes.
4. Activate the app. Keep its Account ID, Client ID, and Client Secret in a local credential store or server environment at implementation time, never in this repository, browser bundle, issue, chat, screenshot, or exported package.
5. Supply the intended host's Zoom user ID or email to the local app. Verify that it lists the expected meeting occurrence, available MP4 layouts, and VTT before importing a class.

## Import behavior to implement

The local app requests an account access token with `grant_type=account_credentials`, lists the host's cloud recordings, and lets the operator choose a meeting occurrence. It downloads the selected MP4 and available transcript using `Authorization: Bearer` and follows redirects. Tokens expire after about one hour; request a new token when needed. Recordings may expose several MP4 layouts or no transcript. Prefer the screen-share-with-speaker layout, but show a choice when layouts differ materially. Poll on app open and explicit Refresh; do not add a public webhook endpoint to the local MVP.

Import promptly after selection and verify byte count and hash. Zoom retention may delete the cloud copy later; downloaded local copies follow this product's explicit-delete policy. Never log tokens or complete authenticated download URLs.

## References checked 2026-09-25

- [Zoom internal apps and role permissions](https://developers.zoom.us/docs/internal-apps/)
- [Create a Server-to-Server OAuth app](https://developers.zoom.us/docs/internal-apps/create/)
- [Server-to-Server token flow](https://developers.zoom.us/docs/internal-apps/s2s-oauth/)
- [Cloud recording endpoints and file types](https://developers.zoom.us/docs/api/meetings/)
- [Recording scope mapping](https://developers.zoom.us/docs/integrations/oauth-scopes-granular/)
- [Enable Zoom audio transcripts](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0065911)
- [App credential handling](https://developers.zoom.us/docs/build-flow/basic-info/app-credentials/)

Recheck the live Zoom app builder, scopes, endpoints, and account settings when implementing; these are time-sensitive external contracts.
