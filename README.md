# OpenDrama Autonomous R&D Agent

A Linux scheduler that checks OpenCode sessions associated with an OpenDrama project and, when no session is actively processing an LLM request, starts/resumes a long-running autonomous R&D task.

## Important behavior

- Uses the OpenCode Server API, not process-name detection.
- Only treats sessions whose `directory` matches the configured project directory as belonging to OpenDrama.
- `busy` and `retry` statuses block a new run.
- Unknown/unresolvable session ownership fails closed (does not start another agent).
- Uses `flock` to prevent concurrent scheduler invocations.
- Persists the OpenCode session ID and progress files between runs.
- Uses a bounded execution window. A timeout does not kill the OpenCode server or claim success.
- Does not push to GitHub or deploy production code automatically.

## Requirements

- Linux (Ubuntu/Debian recommended)
- Python 3.10+
- OpenCode installed and authenticated for the service user
- An OpenCode server bound to `127.0.0.1`
- Git installed
- A dedicated, unprivileged Linux user for this automation

## Install

```bash
sudo useradd --create-home --shell /bin/bash opendrama-agent
sudo mkdir -p /opt/opendrama /opt/opendrama-agent
sudo chown -R opendrama-agent:opendrama-agent /opt/opendrama /opt/opendrama-agent
```

Put this project in `/opt/opendrama-agent`, then:

```bash
cd /opt/opendrama-agent
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
cp config.example.json config.json
```

Edit `config.json` and `.env`. The `project_path` must be the absolute path of the actual OpenDrama checkout. Do not put production secrets in the agent user's environment.

## OpenCode Server

Run the OpenCode server as the same dedicated user that owns the authenticated OpenCode configuration. Keep it loopback-only:

```bash
cd /opt/opendrama
opencode serve --hostname 127.0.0.1 --port 4096
```

Configure Basic Auth using the OpenCode-supported server password environment variable for your installed version. Check the installed version's `opencode serve --help` and API docs before exposing any port. Never expose the unauthenticated server to the public internet.

The server must be the same server instance used by the interactive OpenCode session you want to monitor. A separate server instance may not see sessions created by another instance.

## First-run checks

```bash
curl -fsS http://127.0.0.1:4096/global/health
.venv/bin/python -m opendrama_agent.cli check
.venv/bin/python -m opendrama_agent.cli run
```

If Basic Auth is configured, use the matching credentials in `.env`. The `check` command prints the project sessions and their statuses. Do not enable unattended scheduling until you have verified that an interactive OpenCode session appears in this API and is recognized as belonging to the configured project.

## Schedule: every day at 11:30 Asia/Shanghai

Use a cron implementation that supports `CRON_TZ`:

```cron
CRON_TZ=Asia/Shanghai
30 11 * * * cd /opt/opendrama-agent && /opt/opendrama-agent/.venv/bin/python -m opendrama_agent.cli run >> /opt/opendrama-agent/logs/cron.log 2>&1
```

Alternatively set the server's system timezone to the desired timezone and use a normal cron entry. Verify with `timedatectl` and the cron implementation's documentation.

## Safety model

Run under a dedicated unprivileged account. Keep production credentials, deployment credentials, and destructive access out of this account. The agent is allowed to inspect and modify the project checkout and run tests, but should not deploy, delete production data, push to the default branch, or publish secrets.

Review `.opencode/` permission configuration against the installed OpenCode version. Permission syntax and tool names can change between releases. Do not copy a blanket `* = allow` policy onto a production server without a sandbox and filesystem restrictions.

## State and recovery

- `data/state.json`: scheduler state and session ID.
- `<project>/.automation/PROGRESS.md`: human-readable R&D progress.
- `<project>/.automation/RESULT.json`: agent's claimed result; the scheduler also checks session completion and report existence.
- `logs/`: scheduler logs.

A timeout is recorded as `timeout`; it does not mean the task completed. The next run reuses the previous session when it still exists. The prompt tells the agent to read progress and continue.

## Limitations

1. The scheduler detects OpenCode LLM work only when it is visible to the configured OpenCode server.
2. A `busy` session is an API-level state, not a guarantee that every child process has stopped.
3. The first version uses one bounded autonomous run per daily trigger. It does not promise infinite execution.
4. The agent cannot solve missing credentials, external service outages, or human-only approvals. It records blockers rather than asking questions.
5. Validate the exact API fields and authentication behavior against the OpenCode version installed on your server.
