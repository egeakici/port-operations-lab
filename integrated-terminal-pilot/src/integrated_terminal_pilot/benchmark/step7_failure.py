"""Read-only regression diagnostics. Never evaluates policies or opens scenarios."""
import hashlib
import json
from pathlib import Path
import traceback
import xml.etree.ElementTree as ET


def junit_failures(path):
    """Keep every failing phase and its full traceback, not just the exit code."""
    path=Path(path)
    if not path.is_file():return []
    result=[]
    for case in ET.parse(path).findall('.//testcase'):
        for tag in ('failure','error'):
            for problem in case.findall(tag):
                result.append(dict(classname=case.get('classname',''),name=case.get('name',''),
                    kind=tag,message=problem.get('message',''),traceback=problem.text or ''))
    return result


def show_failures(failures,stream):
    for index,row in enumerate(failures,1):
        stream.write(f'\nFAILURE {index}/{len(failures)}: {row["classname"]}::{row["name"]}\n')
        stream.write(row['message']+'\n'+row['traceback']+'\n')
    stream.flush()


def support_report(root,reason,*,exception=None):
    """One portable text receipt; include all old/new JUnit failures, with hashes.

    Read only lightweight pipeline/regression evidence. No model load, pickle,
    scenarios, scientific result rows or held-out access is performed here.
    """
    root=Path(root);lines=['STEP 7 SUPPORT REPORT',f'Bundle: {root}',f'Reason: {reason}']
    if exception is not None:
        lines+=['', ''.join(traceback.format_exception(type(exception),exception,exception.__traceback__))]
    for name in ('pipeline_status.json','pipeline/FAILED.json'):
        path=root/name
        if path.is_file():lines+=['',name,path.read_text(encoding='utf-8-sig')]
    failures=[]
    for junit in sorted((root/'regressions').glob('*/junit.xml')):
        rows=junit_failures(junit);failures.extend(rows)
        lines+=['',f'JUnit: {junit.relative_to(root)}',
                'SHA256: '+hashlib.sha256(junit.read_bytes()).hexdigest()]
        for row in rows:
            lines += [f'{row["kind"].upper()}: {row["classname"]}::{row["name"]}',row['message'],row['traceback']]
        result=junit.parent/'result.json'
        if result.is_file():lines+=['RESULT:',result.read_text(encoding='utf-8-sig')]
    # Pytest can fail before JUnit exists (collection/import/OS error).
    for log in sorted((root/'pipeline/logs').glob('*/stderr.log')):
        text=log.read_text(encoding='utf-8',errors='replace')
        if text:lines+=['',str(log.relative_to(root)),text[-16000:]]
    for log in sorted((root/'regressions').glob('*/stdout.log')):
        text=log.read_text(encoding='utf-8',errors='replace')
        lines+=['',str(log.relative_to(root))+' (tail)',text[-24000:]]
    content='\n'.join(lines)+'\n';sha=hashlib.sha256(content.encode('utf-8')).hexdigest()
    directory=root/'support';directory.mkdir(parents=True,exist_ok=True)
    target=directory/('support_'+sha[:16]+'.txt')
    if not target.exists():
        with target.open('x',encoding='utf-8',newline='\n') as stream:stream.write(content)
    elif target.read_bytes()!=content.encode('utf-8'):raise RuntimeError('support receipt collision')
    return dict(path=str(target),sha256=sha,failures=len(failures))
