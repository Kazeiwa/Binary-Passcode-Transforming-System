#!/usr/bin/env python3
"""Build/test/archive on a Mac with Xcode. Nothing is uploaded by this script."""
import argparse,json,platform,plistlib,shutil,subprocess,sys,zipfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def run(args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)
def main():
    p=argparse.ArgumentParser(description='Build binary_image_passcode V2.6 for iOS')
    p.add_argument('--test',action='store_true',help='Run the included native XCTest suite in an available simulator')
    p.add_argument('--unsigned',action='store_true',help='Build an unsigned IPA; must be signed before installation')
    p.add_argument('--team',help='Apple Developer Team ID for automatic signing')
    p.add_argument('--bundle-id',default='org.binarypasscode.image.ios',help='Use a bundle identifier registered to your team')
    p.add_argument('--method',choices=['debugging','release-testing','app-store-connect'],default='debugging')
    p.add_argument('--destination',help='Override the simulator destination for tests')
    p.add_argument('--output',type=Path,default=ROOT/'dist')
    a=p.parse_args()
    if platform.system()!='Darwin' or not shutil.which('xcodebuild'):
        p.exit(2,'This build requires macOS and a full Xcode installation. No IPA was produced.\n')
    if not a.test and not a.unsigned and not a.team:p.error('Choose --test, --unsigned, or supply --team TEAMID for a signed IPA.')
    run(['xcodebuild','-version']);run([sys.executable,ROOT/'generate_project.py'])
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    common=['xcodebuild','-project','binary_image_passcode.xcodeproj','-scheme','binary_image_passcode','-derivedDataPath',out/'DerivedData']
    if a.test:
        destination=a.destination
        if destination and 'platform=iOS Simulator' not in destination:
            p.error('--test only supports iOS Simulator destinations; device signing must use your own team.')
        if not destination:
            devices=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','--json']))['devices']
            candidates=[d for runtime,ds in devices.items() if 'iOS' in runtime for d in ds if d.get('isAvailable') and 'iPhone' in d['name']]
            if not candidates:p.exit(2,'No available iPhone simulator. Install an iOS Simulator runtime in Xcode Settings.\n')
            destination='platform=iOS Simulator,id='+candidates[0]['udid']
        result=out/'NativeTests.xcresult'
        if result.exists():result=out/('NativeTests-'+time.strftime('%Y%m%d-%H%M%S')+'.xcresult')
        # A completely unsigned simulator app loses its Keychain entitlements.
        # Local ad-hoc signing needs no Apple account or developer certificate.
        run(common+['test','-configuration','Debug','-destination',destination,'-resultBundlePath',result,
                    'CODE_SIGNING_ALLOWED=YES','CODE_SIGNING_REQUIRED=YES','CODE_SIGN_IDENTITY=-',
                    'CODE_SIGN_STYLE=Manual','DEVELOPMENT_TEAM='])
        if not a.unsigned and not a.team:return
    archive=out/'binary_image_passcode.xcarchive'
    command=common+['archive','-configuration','Release','-destination','generic/platform=iOS','-archivePath',archive,'PRODUCT_BUNDLE_IDENTIFIER='+a.bundle_id]
    if a.unsigned:
        run(command+['CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO','CODE_SIGN_IDENTITY='])
        app=archive/'Products/Applications/binary_image_passcode.app'
        if not (app/'binary_image_passcode').is_file():p.exit(1,'Archive has no executable; refusing to package.\n')
        target=out/'binary_image_passcode_v2.6_unsigned.ipa'
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
            for path in sorted(app.rglob('*')):
                if path.is_file():z.write(path,'Payload/'+app.name+'/'+path.relative_to(app).as_posix())
        print('Unsigned IPA (not directly installable):',target)
    else:
        run(command+['DEVELOPMENT_TEAM='+a.team,'-allowProvisioningUpdates'])
        options={'method':a.method,'teamID':a.team,'destination':'export','signingStyle':'automatic','manageAppVersionAndBuildNumber':False,'stripSwiftSymbols':True}
        file=out/'ExportOptions.plist';file.write_bytes(plistlib.dumps(options))
        run(['xcodebuild','-exportArchive','-archivePath',archive,'-exportOptionsPlist',file,'-exportPath',out/'signed','-allowProvisioningUpdates'])
        print('Signed export:',out/'signed')
if __name__=='__main__':main()
