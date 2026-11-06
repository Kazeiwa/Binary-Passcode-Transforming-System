"""Deterministic Xcode project, no XcodeGen/CocoaPods dependency. Python 3.9+."""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent
def uid(s):return hashlib.sha256(s.encode()).hexdigest()[:24].upper()
def q(s):return json.dumps(str(s),ensure_ascii=False)
objects={}
def add(identity,kind,**values):
    ident=uid(identity);objects[ident]={'isa':kind,**values};return ident
def raw(s):return ('RAW',s)
def dump(v):
    if isinstance(v,tuple) and v[0]=='RAW':return v[1]
    if isinstance(v,dict):return '{ '+''.join(f'{q(k) if any(c in k for c in "[]*") else k} = {dump(a)}; ' for k,a in v.items())+'}'
    if isinstance(v,list):return '( '+', '.join(dump(a) for a in v)+' )'
    return q(v)
def ref(path,kind):return add('file:'+path,'PBXFileReference',lastKnownFileType=kind,path=path,sourceTree='<group>')
sources=sorted(list((ROOT/'App').glob('*.swift'))+list((ROOT/'App').glob('*.mm'))+list((ROOT/'Core').glob('*.cpp'))+list((ROOT/'Core').glob('*.mm')))
files=[];build=[]
for path in sources:
    rel=path.relative_to(ROOT).as_posix();ext=path.suffix
    f=ref(rel,{'swift':'sourcecode.swift','.mm':'sourcecode.cpp.objcpp','.cpp':'sourcecode.cpp.cpp'}.get(ext,'sourcecode.swift'));files.append(f)
    build.append(add('build:'+rel,'PBXBuildFile',fileRef=raw(f)))
headers=sorted(list((ROOT/'App').glob('*.h'))+list((ROOT/'Core').glob('*.hpp')))
for path in headers:files.append(ref(path.relative_to(ROOT).as_posix(),'sourcecode.c.h'))
resources=[]
for path,kind in [('Assets.xcassets','folder.assetcatalog'),('PrivacyInfo.xcprivacy','text.xml')]:
    f=ref(path,kind);files.append(f);resources.append(add('build:'+path,'PBXBuildFile',fileRef=raw(f)))
files.append(ref('Info.plist','text.plist.xml'))
files.append(ref('App/Simulator.entitlements','text.plist.entitlements'))
app=add('product:app','PBXFileReference',explicitFileType='wrapper.application',includeInIndex='0',path='binary_image_passcode.app',sourceTree='BUILT_PRODUCTS_DIR')
testproduct=add('product:test','PBXFileReference',explicitFileType='wrapper.cfbundle',includeInIndex='0',path='NativeTests.xctest',sourceTree='BUILT_PRODUCTS_DIR')
uiproduct=add('product:uitest','PBXFileReference',explicitFileType='wrapper.cfbundle',includeInIndex='0',path='KeyManagerUITests.xctest',sourceTree='BUILT_PRODUCTS_DIR')
testfile=ref('Tests/NativeTests.swift','sourcecode.swift');files.append(testfile)
uifile=ref('Tests/KeyManagerUITests.swift','sourcecode.swift');files.append(uifile)
fixtures=ref('Tests/Fixtures','folder');files.append(fixtures)
testbuild=add('testbuild','PBXBuildFile',fileRef=raw(testfile));fixturebuild=add('fixturesbuild','PBXBuildFile',fileRef=raw(fixtures))
uibuild=add('uibuild','PBXBuildFile',fileRef=raw(uifile))
def phase(name,kind,items):return add(name,kind,buildActionMask='2147483647',files=[raw(x) for x in items],runOnlyForDeploymentPostprocessing='0')
src=phase('sources','PBXSourcesBuildPhase',build);res=phase('resources','PBXResourcesBuildPhase',resources);fw=phase('frameworks','PBXFrameworksBuildPhase',[])
tsrc=phase('testsources','PBXSourcesBuildPhase',[testbuild]);tres=phase('testresources','PBXResourcesBuildPhase',[fixturebuild]);tfw=phase('testframeworks','PBXFrameworksBuildPhase',[])
uisrc=phase('uisources','PBXSourcesBuildPhase',[uibuild]);uires=phase('uiresources','PBXResourcesBuildPhase',[]);uifw=phase('uiframeworks','PBXFrameworksBuildPhase',[])
def configList(name,base):
    configs=[]
    for configuration in ['Debug','Release']:
        settings=dict(base)
        settings.update({'SWIFT_OPTIMIZATION_LEVEL':'-Onone' if configuration=='Debug' else '-O','GCC_OPTIMIZATION_LEVEL':'0' if configuration=='Debug' else '2','DEBUG_INFORMATION_FORMAT':'dwarf' if configuration=='Debug' else 'dwarf-with-dsym'})
        if configuration=='Debug':settings.update(ENABLE_TESTABILITY='YES',SWIFT_ACTIVE_COMPILATION_CONDITIONS='DEBUG',GCC_PREPROCESSOR_DEFINITIONS=['DEBUG=1','$(inherited)'])
        configs.append(add(name+configuration,'XCBuildConfiguration',buildSettings=settings,name=configuration))
    return add(name+'configs','XCConfigurationList',buildConfigurations=[raw(x) for x in configs],defaultConfigurationIsVisible='0',defaultConfigurationName='Release')
common={'CLANG_ENABLE_MODULES':'YES','CLANG_ENABLE_OBJC_ARC':'YES','CLANG_CXX_LANGUAGE_STANDARD':'c++17','CLANG_CXX_LIBRARY':'libc++','SWIFT_VERSION':'5.0','IPHONEOS_DEPLOYMENT_TARGET':'16.0','SDKROOT':'iphoneos','TARGETED_DEVICE_FAMILY':'1,2','SUPPORTED_PLATFORMS':'iphoneos iphonesimulator','CODE_SIGN_STYLE':'Automatic','ENABLE_BITCODE':'NO','SWIFT_STRICT_CONCURRENCY':'minimal','ENABLE_USER_SCRIPT_SANDBOXING':'YES'}
pcfg=configList('project',common)
acfg=configList('app',{'PRODUCT_NAME':'binary_image_passcode','PRODUCT_MODULE_NAME':'binary_image_passcode','PRODUCT_BUNDLE_IDENTIFIER':'org.binarypasscode.image.ios','INFOPLIST_FILE':'Info.plist','SWIFT_OBJC_BRIDGING_HEADER':'App/Bridging.h','ASSETCATALOG_COMPILER_APPICON_NAME':'AppIcon','LD_RUNPATH_SEARCH_PATHS':['$(inherited)','@executable_path/Frameworks'],'CURRENT_PROJECT_VERSION':'26','MARKETING_VERSION':'2.6','CODE_SIGN_ENTITLEMENTS[sdk=iphonesimulator*]':'App/Simulator.entitlements'})
tcfg=configList('test',{'PRODUCT_NAME':'NativeTests','PRODUCT_BUNDLE_IDENTIFIER':'org.binarypasscode.image.ios.tests','GENERATE_INFOPLIST_FILE':'YES','SWIFT_OBJC_BRIDGING_HEADER':'App/Bridging.h','TEST_HOST':'$(BUILT_PRODUCTS_DIR)/binary_image_passcode.app/binary_image_passcode','BUNDLE_LOADER':'$(TEST_HOST)','LD_RUNPATH_SEARCH_PATHS':['$(inherited)','@executable_path/Frameworks','@loader_path/Frameworks']})
uicfg=configList('uitest',{'PRODUCT_NAME':'KeyManagerUITests','PRODUCT_BUNDLE_IDENTIFIER':'org.binarypasscode.image.ios.uitests','GENERATE_INFOPLIST_FILE':'YES','TEST_TARGET_NAME':'binary_image_passcode','LD_RUNPATH_SEARCH_PATHS':['$(inherited)','@executable_path/Frameworks','@loader_path/Frameworks']})
target=add('appTarget','PBXNativeTarget',buildConfigurationList=raw(acfg),buildPhases=[raw(src),raw(fw),raw(res)],buildRules=[],dependencies=[],name='binary_image_passcode',productName='binary_image_passcode',productReference=raw(app),productType='com.apple.product-type.application')
proxy=add('proxy','PBXContainerItemProxy',containerPortal=raw(uid('project')),proxyType='1',remoteGlobalIDString=raw(target),remoteInfo='binary_image_passcode')
dep=add('testDependency','PBXTargetDependency',target=raw(target),targetProxy=raw(proxy))
test=add('testTarget','PBXNativeTarget',buildConfigurationList=raw(tcfg),buildPhases=[raw(tsrc),raw(tfw),raw(tres)],buildRules=[],dependencies=[raw(dep)],name='NativeTests',productName='NativeTests',productReference=raw(testproduct),productType='com.apple.product-type.bundle.unit-test')
uidep=add('uiTestDependency','PBXTargetDependency',target=raw(target),targetProxy=raw(proxy))
uitest=add('uiTestTarget','PBXNativeTarget',buildConfigurationList=raw(uicfg),buildPhases=[raw(uisrc),raw(uifw),raw(uires)],buildRules=[],dependencies=[raw(uidep)],name='KeyManagerUITests',productName='KeyManagerUITests',productReference=raw(uiproduct),productType='com.apple.product-type.bundle.ui-testing')
products=add('products','PBXGroup',children=[raw(app),raw(testproduct),raw(uiproduct)],name='Products',sourceTree='<group>')
main=add('main','PBXGroup',children=[raw(x) for x in files]+[raw(products)],sourceTree='<group>')
project=add('project','PBXProject',attributes={'BuildIndependentTargetsInParallel':'YES','LastUpgradeCheck':'1600','TargetAttributes':{target:{'CreatedOnToolsVersion':'16.0'},test:{'CreatedOnToolsVersion':'16.0','TestTargetID':target},uitest:{'CreatedOnToolsVersion':'16.0','TestTargetID':target}}},buildConfigurationList=raw(pcfg),compatibilityVersion='Xcode 14.0',developmentRegion='zh_CN',hasScannedForEncodings='0',knownRegions=['zh_CN','en','Base'],mainGroup=raw(main),productRefGroup=raw(products),projectDirPath='',projectRoot='',targets=[raw(target),raw(test),raw(uitest)])
p=ROOT/'binary_image_passcode.xcodeproj';p.mkdir(exist_ok=True)
content='// !$*UTF8*$!\n'+dump({'archiveVersion':'1','classes':{},'objectVersion':'56','objects':objects,'rootObject':raw(project)})+'\n'
(p/'project.pbxproj').write_text(content,encoding='utf-8')
scheme=ET.Element('Scheme',LastUpgradeVersion='1600',version='1.3')
def buildable(parent,id,name):ET.SubElement(parent,'BuildableReference',BuildableIdentifier='primary',BlueprintIdentifier=id,BuildableName=name,BlueprintName={target:'binary_image_passcode',test:'NativeTests',uitest:'KeyManagerUITests'}[id],ReferencedContainer='container:binary_image_passcode.xcodeproj')
action=ET.SubElement(scheme,'BuildAction',parallelizeBuildables='YES',buildImplicitDependencies='YES');entries=ET.SubElement(action,'BuildActionEntries');entry=ET.SubElement(entries,'BuildActionEntry',buildForTesting='YES',buildForRunning='YES',buildForProfiling='YES',buildForArchiving='YES',buildForAnalyzing='YES');buildable(entry,target,'binary_image_passcode.app')
action=ET.SubElement(scheme,'TestAction',buildConfiguration='Debug',selectedDebuggerIdentifier='Xcode.DebuggerFoundation.Debugger.LLDB',selectedLauncherIdentifier='Xcode.IDEFoundation.Launcher.LLDB',shouldUseLaunchSchemeArgsEnv='YES');tests=ET.SubElement(action,'Testables');testable=ET.SubElement(tests,'TestableReference',skipped='NO');buildable(testable,test,'NativeTests.xctest')
uitestable=ET.SubElement(tests,'TestableReference',skipped='NO');buildable(uitestable,uitest,'KeyManagerUITests.xctest')
launch=ET.SubElement(scheme,'LaunchAction',buildConfiguration='Debug',selectedDebuggerIdentifier='Xcode.DebuggerFoundation.Debugger.LLDB',selectedLauncherIdentifier='Xcode.IDEFoundation.Launcher.LLDB',launchStyle='0',useCustomWorkingDirectory='NO',ignoresPersistentStateOnLaunch='NO',debugDocumentVersioning='YES',debugServiceExtension='internal',allowLocationSimulation='YES');run=ET.SubElement(launch,'BuildableProductRunnable',runnableDebuggingMode='0');buildable(run,target,'binary_image_passcode.app')
ET.SubElement(scheme,'ProfileAction',buildConfiguration='Release',shouldUseLaunchSchemeArgsEnv='YES',savedToolIdentifier='',useCustomWorkingDirectory='NO',debugDocumentVersioning='YES')
ET.SubElement(scheme,'AnalyzeAction',buildConfiguration='Debug');ET.SubElement(scheme,'ArchiveAction',buildConfiguration='Release',revealArchiveInOrganizer='YES')
schemedir=p/'xcshareddata/xcschemes';schemedir.mkdir(parents=True,exist_ok=True);ET.indent(scheme);ET.ElementTree(scheme).write(schemedir/'binary_image_passcode.xcscheme',encoding='UTF-8',xml_declaration=True)
print('Generated',p.name)
