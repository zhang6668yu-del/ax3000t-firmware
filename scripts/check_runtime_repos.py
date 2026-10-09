import json
import pathlib
import subprocess
import sys
import tempfile

base, out = (pathlib.Path(x).resolve() for x in sys.argv[1:3])
roots = [p.parent.parent for p in base.glob('build_dir/target-*/root-*/etc/openwrt_release')]
assert len(roots) == 1, roots
root = roots[0]
lines = []
for path in [root/'etc/apk/repositories', *sorted((root/'etc/apk/repositories.d').glob('*'))]:
    if path.is_file():
        lines.extend(s for s in path.read_text().splitlines() if s.strip() and not s.lstrip().startswith('#'))
assert lines and all(line.startswith('https://') for line in lines), lines
assert any('/25.12.5/targets/mediatek/filogic/' in line for line in lines), lines
assert any('/packages-25.12/aarch64_cortex-a53/passwall_packages/' in line for line in lines), lines
assert not any('snapshot' in line.lower() for line in lines), lines
apk = base/'staging_dir/host/bin/apk'
with tempfile.TemporaryDirectory() as tmp:
    repo = pathlib.Path(tmp)/'repositories'
    repo.write_text('\n'.join(lines)+'\n')
    # Native host APK reads the target's installed database and shipped keys.
    # --simulate checks resolution without installing or running target scripts.
    command = [str(apk),'--root',str(root),'--arch','aarch64_cortex-a53','--keys-dir',str(root/'etc/apk/keys'),'--repositories-file',str(repo)]
    results = []
    for arguments in [['update'], ['add','--simulate','sing-box'], ['add','--simulate','luci-app-passwall']]:
        run = subprocess.run(command+arguments, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        results.append({'arguments':arguments,'exit_code':run.returncode,'output':run.stdout})
        print(run.stdout, flush=True)
        assert run.returncode == 0, arguments
        assert not any(s in run.stdout for s in ['UNTRUSTED','BAD signature','temporary error','No such file or directory','unable to select packages']), run.stdout
    (out/'repository-install-check.json').write_text(json.dumps({'repositories':lines,'checks':results,'note':'Dependency resolution on GitHub runner; does not prove WAN/DNS or ARM runtime on the router.'},indent=2)+'\n')
