# Sewa Setu — Old Age Pension Portal

An in-house portal for the Department of Social Welfare, Government of
Purvanchal. It supports pension applications, departmental review, and
authenticated AI-assistant integrations through separate citizen and officer
MCP servers.

## Contents

- [Quick start](#quick-start)
- [Run the whole application](#run-the-whole-application)
- [Local services](#local-services)
- [Application behavior](#application-behavior)
- [MCP assistant integration](#mcp-assistant-integration)
- [OAuth authorization server](#oauth-authorization-server)
- [Persona evaluations](#persona-evaluations)
- [Production deployment](#production-deployment)
- [Project layout](#project-layout)

## Quick start

1. If you do not already have a local `.env` file, copy [`.env.example`](.env.example)
   to `.env`.
2. Set a strong `ADMIN_PASSWORD` in `.env`.
3. Build and start the services:

   ```sh
   docker compose up --build
   ```

The first database startup loads the schema and the seed data. The seed contains
approximately 100,000 applications.

To stop the services, press `Ctrl+C`. If they were started in detached mode, use:

```sh
docker compose down
```

## Run the whole application

Follow these steps to start the local stack, submit and review an application,
check its status, and then stop the stack.

### 1. Prepare the environment

Install Docker Desktop (including Docker Compose) and make sure Docker is
running. From the repository root, create a local environment file if you do
not already have one:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace `ADMIN_PASSWORD` with a strong local password. The
default `ADMIN_USERNAME` is `admin`. Keep `.env` private and do not commit it.
The example configuration uses local URLs and enables MCP access for the
**Sonari** block by default.

### 2. Build and start the services

Run this from the repository root:

```sh
docker compose up --build -d
```

This starts the portal, PostgreSQL database, simulated SMS gateway, nightly
scheduler, and both MCP servers. On the database's first startup, Compose loads
the schema and seed data. Check that the services are running:

```sh
docker compose ps
```

Open <http://localhost:8000> in a browser. If a service is still starting,
wait a few seconds and refresh. To inspect startup output:

```sh
docker compose logs -f app
```

Press `Ctrl+C` to stop viewing logs; this does not stop the services.

### 3. Submit a citizen application

Use synthetic or otherwise authorized test information when trying the local
application flow.

1. Open <http://localhost:8000/apply>.
2. Enter a 10-digit mobile number and solve the displayed security question.
3. Open the simulated SMS console at <http://localhost:8000/__gateway/> and
   retrieve the latest OTP for that number. Enter it at the verification page.
   The OTP is valid for five minutes.
4. Complete the personal details, address, and bank details. The date of birth
   must be entered as `DD/MM/YYYY`; the applicant must be at least 60 years old.
5. Upload an age-proof document in PDF, JPG, or PNG format (maximum 5 MB).
6. Review the details and validation messages on the declaration page. Confirm
   the declaration to submit.
7. Save the application number shown on the confirmation page. The applicant
   can download the acknowledgment PDF and check the application from the status
   page.

The application window, required fields, supported blocks, bank account and
IFSC formats, age-proof file, and duplicate active application rules are
validated when the application is submitted. The database is seeded only when
its data volume is first created; restarting the services keeps the existing
database.

### 4. Check application status

Open <http://localhost:8000/status> and sign in with the application's mobile
number and the applicant's date of birth as the password, in `DDMMYYYY` format.
The status page shows the latest application, its status, and a link to the
acknowledgment PDF. A pending application can be withdrawn there if a fresh
application is needed.

### 5. Review the application as an administrator

1. Open <http://localhost:8000/admin>.
2. Sign in with `ADMIN_USERNAME` (default: `admin`) and the `ADMIN_PASSWORD`
   from `.env`.
3. Open the application queue and select the pending application to inspect its
   details and audit history.
4. Approve or reject the pending application as appropriate.

The applicant can sign in to the status page again to see the updated decision.
The portal also runs the deemed-approval job on the scheduler according to the
15-day SLA described above.

### 6. Connect an MCP assistant (optional)

The MCP endpoints are included in [`.vscode/mcp.json`](.vscode/mcp.json). With
the stack running, open the repository in VS Code and connect to the citizen or
officer MCP server from an OAuth-capable MCP client. Complete sign-in and
consent for the matching resource. Citizens use the citizen endpoint and
citizen consent; officers use the officer endpoint and officer consent. Never
share a citizen token with the officer server or vice versa.

The citizen assistant can read scheme information, submit an application for
the authenticated citizen, and check that citizen's application. The officer
assistant can list enabled-block pending applications, review a case and audit
trail, and record an approval or rejection with a reason. The MCP block
allowlist is **Sonari** by default. See [MCP assistant integration](#mcp-assistant-integration)
and [OAuth authorization server](#oauth-authorization-server) for details.

### 7. Run evaluations (optional)

Evaluations create and approve synthetic applications. Only run them against an
isolated evaluation deployment with synthetic identities and its own shared
portal/MCP database. Follow the [persona evaluation instructions](#persona-evaluations)
to configure credentials and run the checks; do not use production data.

### 8. Stop the application

Stop the containers while keeping the database volume and its data:

```sh
docker compose down
```

Start the same local deployment again with `docker compose up -d`. Avoid
`docker compose down -v` unless you explicitly intend to permanently remove
the Compose volumes, including the database.

## Local services

| Service | URL | Notes |
| --- | --- | --- |
| Citizen portal | <http://localhost:8000> | Apply for a pension. |
| Applicant status | <http://localhost:8000/status> | Sign in with a mobile number and date of birth in `DDMMYYYY` format. |
| Departmental login | <http://localhost:8000/admin> | Username is `admin` by default; password is `ADMIN_PASSWORD`. |
| SMS gateway console | <http://localhost:8000/__gateway/> | Displays simulated OTPs and notifications after delivery. |
| SMS gateway inbox | <http://localhost:8000/__gateway/api/messages?to=%3Cmobile%3E> | JSON inbox for the supplied mobile number. |
| Citizen MCP server | <http://localhost:8001/mcp> | Streamable HTTP; requires a citizen access token. |
| Officer MCP server | <http://localhost:8002/mcp> | Streamable HTTP; requires an officer access token. |
| Evaluation dashboard | <http://localhost:8000/eval-dashboard> | Shows persona scenarios and evaluation results. |

The SMS gateway simulates carrier delivery latency of approximately 1–4
seconds.

### MCP block allowlist

The default MCP block allowlist is **Sonari**. Set `MCP_ENABLED_BLOCKS` to a
comma-separated subset of portal blocks to change it. This server-side allowlist
applies to agent application submissions, the officer queue, case lookups, and
decisions. It does not change the normal web portal's block coverage.

## Application behavior

The citizen application flow is:

1. Enter a mobile number and verify it with an OTP.
2. Provide personal, address, and bank details.
3. Upload age proof.
4. Review the application and confirm the declaration.
5. Receive an application number.

At submission, `validate_application()` in [`app/app.py`](app/app.py) checks
that:

- The applicant is at least 60 years old.
- Required information and an age-proof document are present.
- The scheme application window is open.
- The mobile number has no other active application (pending, approved, or
  deemed-approved).

A pending application can be withdrawn through the status portal. After
withdrawal, the same mobile number may be used to apply again.

Departmental users can view and filter applications, approve or reject pending
applications, and review each application's audit trail. The nightly job
[`app/scripts/deemed_approval.py`](app/scripts/deemed_approval.py), run by the
`scheduler` container, deems applications approved if they remain pending
beyond the 15-day statutory service-level agreement (SLA).

## MCP assistant integration

The citizen and officer MCP servers are separate so that each assistant receives
only the tools for its role. Their local endpoints are:

- Citizen: <http://localhost:8001/mcp>
- Officer: <http://localhost:8002/mcp>

The workspace includes a VS Code MCP configuration at
[`.vscode/mcp.json`](.vscode/mcp.json). Start the Compose services before
connecting an assistant to these local endpoints.

Both servers require Sewa Setu OAuth 2.1 bearer tokens. They do not accept OTPs,
passwords, or caller-supplied mobile identities. Each server verifies the
portal-issued token's signature, issuer, audience, role, and scope. Citizens
must sign in and consent to the citizen MCP resource; officers must sign in and
consent to the officer resource. Keep the two endpoint URLs and access tokens
separate.

### Citizen tools

| Tool | Purpose |
| --- | --- |
| `pension_scheme_information` | Read current pension rules and blocks enabled for agent applications. |
| `submit_pension_application` | Submit an application for the authenticated citizen, subject to the portal's normal validation. |
| `check_my_application` | Check the latest application associated with the authenticated citizen. |

Application submission requires the applicant's explicit declaration
confirmation and an age-proof file. Accepted formats are PDF, JPG, and PNG, up
to 5 MB. The portal also checks age, required fields, block allowlist, scheme
window, document, IFSC, and duplicate active applications.

### Officer tools

| Tool | Purpose |
| --- | --- |
| `list_pending_applications` | List pending cases in the agent-enabled blocks. |
| `review_application` | Read a case and its audit trail. |
| `decide_on_application` | Approve or reject a pending case with a required reason. |

The portal records the authenticated officer and decision in the application
record and audit log. An officer program token for unattended use can be issued
at `/admin/tokens`; its audience must be the officer MCP resource URL.

For user-consented sessions, complete OAuth sign-in and consent in the assistant
client. On deployment, set `PUBLIC_BASE_URL`, `CITIZEN_RESOURCE_URL`, and
`OFFICER_RESOURCE_URL` to the exact HTTPS URLs used by people and MCP clients.
The token audience must exactly match the resource URL used when the token is
issued.

## OAuth authorization server

Sewa Setu can authorize third-party applications to act for a citizen (scope
`citizen`) or a block officer (scope `officer`) after the person signs in and
approves access. Citizens sign in with their mobile number and OTP; officers use
the departmental login. The third-party application does not handle the
person's OTP or password.

| Capability | Endpoint | Details |
| --- | --- | --- |
| Authorization-server discovery | `/.well-known/oauth-authorization-server` | RFC 8414 metadata. |
| Dynamic client registration | `/oauth/register` | RFC 7591; a client ID metadata document URL can also be used as `client_id`. |
| Authorization | `/oauth/authorize` | Authorization code with PKCE S256. The requested `resource` becomes the token audience (RFC 8707). |
| Token issue and refresh | `/oauth/token` | Access tokens are RS256 JWTs. Refresh tokens rotate within the sign-in session. |
| Token revocation | `/oauth/revoke` | RFC 7009. |
| Signing keys | `/.well-known/jwks.json` | JSON Web Key Set (JWKS) for token verification. |

Sign-in sessions have an absolute end measured from consent: two hours for
citizens and eight hours for officers. Access tokens last 20 minutes for
citizens and 30 minutes for officers. Refreshing a token does not extend the
session; the person must sign in again when it ends. This limits exposure on
shared phones and kiosks.

People can revoke a sign-in through `/oauth/revoke`, from **Connected
applications** in the status portal, or from the officer admin dashboard.

Services that receive these tokens must verify them with the JWKS, check that
`iss` identifies this portal, check that `aud` is their own canonical URL, and
use the `scope`, `role`, and `sub` claims. Subject values are
`citizen:<mobile>` or `officer:<username>`.

## Persona evaluations

The evaluation dashboard at <http://localhost:8000/eval-dashboard> shows
synthetic citizens, scenarios, MCP conversations, database checks, and results.
The runner uses real streamable-HTTP MCP client sessions and checks Postgres
records and audit rows; it does not call a model or infer success from assistant
text.

> **Safety:** The evaluator creates and approves a synthetic application. Run it
> only against an isolated evaluation deployment that uses synthetic identities
> and a database shared by that deployment's portal and MCP services. Do not
> point it at production data.

### Run from your host

Install the MCP dependencies and start the services:

```sh
pip install -r requirements-mcp.txt
docker compose up --build -d
```

Provide these values to the evaluation runner:

| Variable | Value |
| --- | --- |
| `EVAL_DATABASE_URL` | Connection string for the isolated evaluation database. |
| `EVAL_CITIZEN_TOKENS` | JSON object mapping persona IDs in [`evals/personas.json`](evals/personas.json) to fresh citizen tokens for the citizen MCP audience. |
| `EVAL_OFFICER_TOKEN` | Fresh officer token for the officer MCP audience. |
| `CITIZEN_MCP_URL` | Optional override for the citizen MCP endpoint. |
| `OFFICER_MCP_URL` | Optional override for the officer MCP endpoint. |

Tokens require a sign-in and consent for the matching MCP resource and expire
quickly. Never commit live tokens or include them in evaluation results. Without
credentials, the runner records `not_run`; it does not report an evaluation as
passed unless it actually ran. For a host-based run, set the variables in your
shell before starting the runner; the Python process does not load values from
`.env` automatically.

Run the evaluator from a host that can reach the isolated database and both MCP
endpoints:

```sh
python -m evals.run_evals
```

Alternatively, run it from the Compose network:

```sh
docker compose --profile eval run --rm eval-runner
```

For the Compose runner, set the required variables in the local `.env`. Set
`EVAL_DATABASE_URL` to the isolated deployment's database URL. Compose passes
these values to the runner, which reaches the database and MCP services over the
private container network.

## Production deployment

Set `PUBLIC_BASE_URL` to the public address people will use, and set
`CITIZEN_RESOURCE_URL` and `OFFICER_RESOURCE_URL` to the exact public MCP
resource URLs. These canonical URLs are used in OAuth discovery and tokens; a
mismatch can prevent clients from finding the sign-in page or validating token
audiences.

Put the portal and MCP endpoints behind HTTPS. Configure strong secrets and
deployment-specific environment values before starting the services. For
example, in an environment where the variables are already set:

```sh
docker compose up --build -d
```

Do not use the example or local-development credentials for a public
deployment. Keep live access tokens and other secrets out of source control.

## Project layout

```text
app/          Flask portal, templates, configuration, and nightly job
dashboard/    Evaluation dashboard served by the portal
evals/        Synthetic personas, MCP evaluation runner, and results
mcp_servers/  Separate citizen and officer streamable-HTTP MCP servers
seed/         Database seed data
smsgw/        Simulated SMS gateway
tests/        Automated tests
```
