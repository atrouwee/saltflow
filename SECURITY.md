# Security

## What saltFlow is

saltFlow is a local tool. It reads files in your repo and serves a review page from your own machine. It has no
accounts, sends nothing to any server, and collects no data.

Things to know:

- By default the page listens on `127.0.0.1` only, so only your own machine can reach it.
- `saltflow --lan` also answers your local network, so you can review on a phone or tablet. **The page has no login.**
  Anyone on that network can read the product's flows, leave notes and answer decisions (which write to
  `flows/notes.jsonl`), and trigger the terminal views: saltFlow's own read-only commands, and any command the product's
  `flows/saltflow.json` names under `commands`. Use `--lan` only on a network you
  trust, and stop the server when you are done. Never expose it to the internet.
- `saltflow capture` builds and runs your product with the build command in `flows/saltflow.json`, and drives it in a
  browser. Only run it on a repo whose code you trust, as you would `npm run build`.
- `saltflow hook` installs a git hook in the product repo that runs saltFlow after each commit.

## Supported versions

Security fixes go into the latest release only.

## Reporting a vulnerability

Please report privately, not in a public issue: use GitHub's private vulnerability reporting on this repository
(the **Security** tab, then **Report a vulnerability**). Say what you found, how to reproduce it, and which version
(`saltflow --version`). You will get an answer as soon as the maintainer can look at it. Please give us a reasonable
time to fix it before you disclose it.
