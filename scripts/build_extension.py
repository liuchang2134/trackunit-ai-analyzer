"""Build and verify a source-only Chrome extension package without overwriting releases."""
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=('manifest.json','background.js','context.js','trackunit-fault-page.js','trackunit-sensor-page.js','sensor-series-bridge.js','xgss-catalog.js','xgss-research.js','xgss-research-runner.js','research-bridge.js','panel.js','panel.html','panel.css','README.md',
       'assets/xcmg-logo.png','assets/icon16.png','assets/icon32.png','assets/icon48.png','assets/icon128.png',
       'assets/SOURCES.md')


def build():
    source=ROOT/'extension'
    entries={name:(source/name).read_bytes() for name in FILES}
    manifest=json.loads(entries['manifest.json'])
    version=manifest['version']
    assert re.fullmatch(r'\d+\.\d+\.\d+',version)
    assert manifest['manifest_version']==3
    assert manifest['permissions']==['sidePanel','activeTab','scripting']
    assert manifest['host_permissions']==['https://manager.trackunit.com/*','https://new.manager.trackunit.com/*','https://xgss.xcmg.com/*']
    assert manifest['side_panel']['default_path']=='panel.html'
    assert manifest['background']['service_worker']=='background.js'
    assert manifest['content_security_policy']['extension_pages']=="script-src 'self'; object-src 'self'; frame-src http://127.0.0.1:8890 http://127.0.0.1:8892"
    output=ROOT/'dist'/f'jilian-extension-{version}.zip'
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,content in entries.items():archive.writestr(name,content)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None and set(archive.namelist())==set(FILES)
        assert all(archive.read(name)==content for name,content in entries.items())
    result=dict(version=version,path=output.relative_to(ROOT).as_posix(),bytes=output.stat().st_size,
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        files={name:hashlib.sha256(content).hexdigest() for name,content in entries.items()},
        packaged_only=True,chrome_installation_verified=False)
    evidence=ROOT/'docs/evaluation'/f'extension-{version}-package.json'
    with evidence.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':build()
