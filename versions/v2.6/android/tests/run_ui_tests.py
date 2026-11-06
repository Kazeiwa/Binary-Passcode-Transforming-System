"""Run Android UI/Keystore-flow tests on a desktop JDK with Robolectric.

Requires Maven on PATH (or --maven), JDK 17+, Python 3 and dependency-download access.
The test-only AndroidKeyStore provider is never part of the application build.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--maven',default=shutil.which('mvn'))
    parser.add_argument('--cache',type=Path,default=HERE/'.cache/maven')
    args=parser.parse_args()
    if not args.maven:parser.error('Install Maven or provide --maven /path/to/mvn')
    maven=Path(args.maven)
    executable=str(maven.resolve()) if maven.exists() else (shutil.which(args.maven) or args.maven)
    build=HERE/'.cache/ui';build.mkdir(parents=True,exist_ok=True)
    (ROOT/'work').mkdir(exist_ok=True)
    repo=args.cache.resolve();repo.mkdir(parents=True,exist_ok=True)
    cpfile=build/'classpath.txt'
    subprocess.run([executable,'-B','-f',str(HERE/'pom.xml'),'-Dmaven.repo.local='+str(repo),
                    'dependency:build-classpath','-Dmdep.outputFile='+str(cpfile)],check=True)
    paths=[]
    for name in cpfile.read_text().strip().split(os.pathsep):
        path=Path(name)
        if path.suffix=='.aar':
            dest=build/(path.stem+'-classes.jar')
            with zipfile.ZipFile(path) as z:dest.write_bytes(z.read('classes.jar'))
            paths.append(str(dest))
        else:paths.append(str(path))
    classes=build/'classes';classes.mkdir(exist_ok=True)
    paths.insert(0,str(classes));cp=os.pathsep.join(paths)
    sources=sorted((ROOT/'src').rglob('*.java'))+[HERE/'AndroidUiTest.java']
    subprocess.run(['javac','-encoding','UTF-8','-cp',cp,'-d',str(classes),*map(str,sources)],check=True)
    home=build/'java-home';home.mkdir(exist_ok=True)
    tmp=ROOT/'work/tmp';tmp.mkdir(parents=True,exist_ok=True)
    command=['java','-Duser.home='+str(home),'-Djava.io.tmpdir='+str(tmp)]
    for name in ('java.lang','java.util','java.io','java.net','java.security','java.text','jdk.internal.access'):
        command+=['--add-opens=java.base/'+name+'=ALL-UNNAMED']
    command+=['-Drobolectric.dependency.repo.url=https://repo.maven.apache.org/maven2',
              '-Dmaven.repo.local='+str(repo),'-cp',cp,'org.junit.runner.JUnitCore','org.binarypasscode.image.AndroidUiTest']
    subprocess.run(command,check=True,cwd=ROOT)

if __name__=='__main__':main()
