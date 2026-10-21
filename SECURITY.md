# Secrets and credentials

This public repository must not contain real API keys, access tokens, passwords, private keys, or production connection strings.

## New deployment

1. Copy .env.example to .env and keep .env untracked.
2. Generate a strong database password with openssl rand -hex 32 or another secure generator.
3. Set POSTGRES_PASSWORD in your private .env.
4. Set OPENAI_API_KEY, DEEPSEEK_API_KEY and other providers' keys in .env or your hosting provider's secrets manager only.
5. Docker Compose supplies DATABASE_URL to the API. For direct API execution without Compose, explicitly configure DATABASE_URL privately.
6. For Internet access, set distinct strong PUBLIC_DEMO_PASSWORD and PUBLIC_DEMO_ADMIN_PASSWORD.

Docker Compose fails closed when POSTGRES_PASSWORD is missing; source code contains no default database password. Never push .env, key files, or screenshots showing configuration values.

## Existing PostgreSQL data volume

Updating POSTGRES_PASSWORD in .env alone does not update the PostgreSQL role password in an existing volume. If your deployment used the previous example credentials, change the actual database role password interactively.

    docker compose -f docker-compose.yml exec postgres psql -U rag_tender -d rag_tender

Inside psql: enter the backslash-password command for role rag_tender, choose a new strong password interactively, and quit. This avoids storing the password in shell history. Update POSTGRES_PASSWORD and any manually configured DATABASE_URL in your private .env and restart the API.

## Check before pushing

    python scripts/check_tracked_secrets.py
    git status --short
    git ls-files '*.env' '*.pem' '*.key' '*credentials*'

CI runs a redacting scanner on all small text files tracked by Git. It detects common API token formats, private-key blocks, nonempty credentials in example environment files, and hard-coded database defaults. It prints file paths and line numbers only.

This is not a complete history scan. Large/binary files and all old commits are outside its coverage. For more complete repository history detection, install gitleaks and run:

    gitleaks git --redact .

Review GitHub secret scanning alerts where available, along with old agent logs and Actions artifacts.

## If a secret was pushed

1. Immediately revoke/rotate it with the provider, even if deleted from the current version.
2. Replace the key/password in deployed services. Investigate where it appeared, including CI logs, PRs, past branches and exported artifacts.
3. Removing it from HEAD does not remove it from Git history, forks or caches.
4. If a history rewrite is necessary, coordinate git-filter-repo or BFG with all collaborators and make a backup before rewriting shared history. Force-push can invalidate existing clone references, PRs and commit hashes. History rewrite never replaces key revocation.

When reporting a possible leak, mention only the provider, affected paths and whether the key has been revoked. Never copy the key into an issue or chat.
