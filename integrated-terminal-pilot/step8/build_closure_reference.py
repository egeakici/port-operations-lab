"""Package byte-identical small derived inputs for the owner's second computer.

Not an archive verifier, scenario generator or scientific experiment.
"""
from pathlib import Path
import zipfile
from evidence import read, sha, publish_bytes, DEFAULT_BUNDLE
from final_closure import PREVIOUS, PREVIOUS_RELEASE_SHA


def main():
    source=PREVIOUS/'step8_release_manifest.json'
    if sha(source)!=PREVIOUS_RELEASE_SHA: raise ValueError('Predecessor changed')
    manifest=read(source)
    names=['derived_arrays.json','cargo_noninferiority.json','wait_cargo_forecast_diagnostics.json',
           'diagnostic_cost_proxy.json','policy_seed_diagnostics.json','compute_cost.json','closure_status.json']
    names += [p for p in manifest['files'] if p.startswith('figures/')]
    import io
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in ['step8_release_manifest.json']+sorted(names):
            raw=(PREVIOUS/name).read_bytes()
            if name!='step8_release_manifest.json' and sha(PREVIOUS/name)!=manifest['files'][name]['sha256']:
                raise ValueError('Derived reference changed')
            item=zipfile.ZipInfo(name,date_time=(2026,10,25,0,0,0)); item.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(item,raw)
        receipt='09499de0840d7bdc7c152ee0bdf543c95716c86cf97b7273f418e1209b1dca3f.json'
        for filename in (receipt,receipt+'.sha256.json'):
            p=DEFAULT_BUNDLE/'return_verification'/filename
            if filename==receipt and sha(p)!='e903d0dc2f61c686fcdd4942dcfc813a6c05a5ba05f78b5e16dd2736b127e0cc':
                raise ValueError('Original official return receipt differs')
            item=zipfile.ZipInfo('verified_step7_return/'+filename,date_time=(2026,10,25,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(item,p.read_bytes())
    target=Path(__file__).with_name('reference')/'closure_reference_v2.zip'
    publish_bytes(target,stream.getvalue())
    print(dict(path=str(target),bytes=target.stat().st_size,sha256=sha(target),scientific_episodes=0))


if __name__=='__main__': main()
