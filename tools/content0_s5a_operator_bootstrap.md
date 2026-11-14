# CONTENT-0 isolated test-operator bootstrap

Use only a fresh stand copied by the project snapshot procedure. The stand
services must be stopped, its snapshot receipt must name this exact stand, and
the original client and bundle must already be configured and verified. The
script checks process marker files; the operator must also verify that no stand
processes are running. Run from the checkout containing these tools.

```powershell
$env:WOT091_TEST_LAB = '1'
$stand = 'C:\path\to\checkout\local\stands\fresh-stand'
$config = 'D:\path\to\project.local.json'
$original = 'C:\path\to\verified-original-client'

python tools/content0_s5a_operator_bootstrap.py backup --stand $stand
python tools/content0_s5a_operator_bootstrap.py identity --stand $stand
```

Copy the UUID printed by `identity` into `$account` below. Do not print or
copy the password from the restricted `private-operator/credentials.json` into
commands, logs or receipts. This account is new and its email uses
`example.test`; it is not an existing player identity.

```powershell
$account = 'replace-with-printed-uuid'
python tools/content0_s5a_operator_bootstrap.py stage --stand $stand --account $account --config $config --original-root $original
python tools/content0_s5a_operator_onboard.py --stand $stand --account $account --stage (Join-Path $stand 'operator-staging\stage-test-lab\game.sqlite') --config $config --original-root $original
python tools/content0_s5a_operator_bootstrap.py activate --stand $stand --account $account --config $config --original-root $original
```

Onboarding records its receipt in `operator-staging/onboard-receipt.json`.
The activation phase calls the project's pool, mixed-ammunition and ammo-loss
workers in order; late-results and access lists are stand configuration, not
automatic grants. Check both database integrity and foreign keys, owner profile,
crew, vehicle, policies, and the unchanged pre-existing owners before running a
service. The script does not establish native login, rendering, or live battle
compatibility. These remain NOT_RUN until tested on the authorized client.

Backups are under `backup-before-operator`. Restore both databases only with
services stopped and after handling any SQLite WAL files. A failed phase can
leave a fresh private/staging directory, or a partially activated new owner;
inspect it and restore the backups before starting again. Do not repurpose an
old or foreign account to recover from an error.
