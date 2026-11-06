package org.binarypasscode.image;

import org.junit.*;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.*;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.shadows.*;
import android.app.*;
import android.content.*;
import android.view.*;
import android.widget.*;
import java.io.*;
import java.security.*;
import java.security.cert.Certificate;
import java.security.spec.AlgorithmParameterSpec;
import java.time.Duration;
import java.util.*;
import javax.crypto.*;
import javax.crypto.spec.SecretKeySpec;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(manifest=Config.NONE,sdk=28)
@GraphicsMode(GraphicsMode.Mode.LEGACY)
public class AndroidUiTest {
    public static class FakeProvider extends Provider{public FakeProvider(){super("AndroidKeyStore",1.0,"Test-only in-memory platform keystore");put("KeyStore.AndroidKeyStore",Store.class.getName());put("KeyGenerator.AES",Generator.class.getName());}}
    public static class Store extends KeyStoreSpi{
        static Map<String,Key>records=new HashMap<>();
        public Key engineGetKey(String a,char[]p){return records.get(a);}public Certificate[]engineGetCertificateChain(String a){return null;}public Certificate engineGetCertificate(String a){return null;}public Date engineGetCreationDate(String a){return new Date();}public void engineSetKeyEntry(String a,Key k,char[]p,Certificate[]c){records.put(a,k);}public void engineSetKeyEntry(String a,byte[]k,Certificate[]c){}public void engineSetCertificateEntry(String a,Certificate c){}public void engineDeleteEntry(String a){records.remove(a);}public Enumeration<String>engineAliases(){return Collections.enumeration(records.keySet());}public boolean engineContainsAlias(String a){return records.containsKey(a);}public int engineSize(){return records.size();}public boolean engineIsKeyEntry(String a){return records.containsKey(a);}public boolean engineIsCertificateEntry(String a){return false;}public String engineGetCertificateAlias(Certificate c){return null;}public void engineStore(OutputStream o,char[]p){}public void engineLoad(InputStream i,char[]p){}
    }
    public static class Generator extends KeyGeneratorSpi{
        public void engineInit(SecureRandom s){}public void engineInit(int n,SecureRandom s){}public void engineInit(AlgorithmParameterSpec p,SecureRandom s){}public SecretKey engineGenerateKey(){SecretKey k=new SecretKeySpec(Crypto.random(32),"AES");Store.records.put(KeyVault.ALIAS,k);return k;}
    }
    @Before public void provider(){Security.removeProvider("AndroidKeyStore");Security.addProvider(new FakeProvider());}
    MainActivity start(){ActivityController<MainActivity>c=Robolectric.buildActivity(MainActivity.class);c.get().setTheme(android.R.style.Theme_Material_Light_NoActionBar);return c.setup().visible().get();}
    static void collect(View v,List<TextView>out){if(v instanceof TextView)out.add((TextView)v);if(v instanceof ViewGroup)for(int i=0;i<((ViewGroup)v).getChildCount();i++)collect(((ViewGroup)v).getChildAt(i),out);}
    @Test public void launchTabsPromptsAndCount()throws Exception{MainActivity a=start();assertEquals(0,a.selectedTab);for(int i=0;i<3;i++){a.tabs[i].performClick();assertEquals(i,a.selectedTab);}a.tabs[0].performClick();a.plain.setText("中文abc");ShadowLooper.idleMainLooper(500,java.util.concurrent.TimeUnit.MILLISECONDS);assertTrue(a.count.getText().toString().startsWith("15 /"));ArrayList<TextView>all=new ArrayList<>();for(View p:a.panels)collect(p,all);for(TextView t:all){String s=t.getText().toString();assertFalse(s.contains("V2.0"));assertFalse(s.contains("时间戳"));assertFalse(s.contains("开发者"));}assertEquals(0,a.keys.size());assertEquals(View.GONE,a.progress.getVisibility());a.finish();}
    @Test public void keyVaultCrudBackupAndTamper()throws Exception{MainActivity a=start();String key=Crypto.generate(),second=Crypto.generate();String id=a.vault.add("朋友",key);a.vault.add("其他",second);a.refreshKeys(id);assertEquals(key,a.selectedKey(0));a.vault.rename(id,"朋友A");a.vault.setDefault(id);assertEquals(id,a.vault.defaultId());byte[]stored=KeyVault.read(new FileInputStream(a.vault.file.getBaseFile()),1048576);assertFalse(new String(stored,"UTF-8").contains(key));assertFalse(new String(stored,"UTF-8").contains("朋友A"));KeyVault reopen=new KeyVault(a);assertEquals(key,reopen.find(id).getString("key"));char[]pass="a strong test password 123".toCharArray();byte[]backup=a.vault.backup(pass);a.vault.delete(id);assertEquals(1,a.vault.list().size());assertEquals(1,a.vault.restore(backup,pass));assertEquals(2,a.vault.list().size());assertEquals(0,a.vault.restore(backup,pass));boolean rejected=false;backup[backup.length-1]^=1;try{a.vault.restore(backup,pass);}catch(Exception e){rejected=true;}assertTrue(rejected);assertEquals(2,a.vault.list().size());a.finish();}
    @Test public void dialogValidationAndCancellation()throws Exception{MainActivity a=start();a.keyDialog(false);ShadowLooper.idleMainLooper();AlertDialog d=ShadowAlertDialog.getLatestAlertDialog();assertTrue(d.isShowing());d.getButton(-1).performClick();ShadowLooper.idleMainLooper();AlertDialog error=ShadowAlertDialog.getLatestAlertDialog();assertNotSame(d,error);assertEquals(0,a.vault.list().size());error.dismiss();d.dismiss();a.runJob("test",()->{Thread.sleep(3000);return null;},o->fail("cancelled task completed"));a.requestCancel();long limit=System.currentTimeMillis()+5000;while(a.busy&&System.currentTimeMillis()<limit){Thread.sleep(25);ShadowLooper.idleMainLooper();}assertFalse(a.busy);assertTrue(a.status.getText().toString().contains("取消"));a.finish();}
    @Test public void streamingPngAndImageSelection()throws Exception{MainActivity a=start();int[]p=new int[560*560];Arrays.fill(p,0xff908070);Transport.Image image=new Transport.Image(560,560,p);File file=new File(a.getCacheDir(),"test.png");Images.png(image,file);UriProvider.register(a,file);int[]size=Images.bounds(a,android.net.Uri.parse("content://org.binarypasscode.test/image"));assertArrayEquals(new int[]{560,560},size);a.finish();}
    @Test public void vaultRecovery()throws Exception{
        MainActivity a=start();String key=Crypto.generate(),id=a.vault.add("恢复测试",key);char[]password="test backup password 123".toCharArray();byte[]backup=a.vault.backup(password);File base=a.vault.file.getBaseFile(),bak=new File(base.getPath()+".bak");java.nio.file.Files.move(base.toPath(),bak.toPath());KeyVault recovered=new KeyVault(a);assertEquals(key,recovered.find(id).getString("key"));try(FileOutputStream out=new FileOutputStream(base)){out.write(new byte[]{1,2,3});}MainActivity broken=start();ShadowLooper.idleMainLooper();AlertDialog d=ShadowAlertDialog.getLatestAlertDialog();assertTrue("recovery dialog visible",d.isShowing());d.getButton(-1).performClick();ShadowLooper.idleMainLooper();assertNotNull("rebuilt UI",broken.root);assertEquals(2,broken.selectedTab);assertEquals(0,broken.vault.list().size());assertEquals(1,broken.vault.restore(backup,password));assertTrue("damaged record preserved: "+Arrays.toString(broken.getFilesDir().list()),Arrays.stream(broken.getFilesDir().list()).anyMatch(n->n.startsWith("unreadable-keys-")));broken.finish();a.finish();
    }
    @Test @Config(manifest=Config.NONE,sdk=35,qualifiers="w393dp-h873dp-xhdpi") @GraphicsMode(GraphicsMode.Mode.NATIVE)
    public void renderNativeScreensAndLoadPixels()throws Exception{
        MainActivity a=start();String id=a.vault.add("示例联系人",Crypto.generate());a.refreshKeys(id);a.plain.setText("This is a private message. 你好，世界。");ShadowLooper.idleMainLooper(500,java.util.concurrent.TimeUnit.MILLISECONDS);
        for(int tab=0;tab<3;tab++){a.select(tab);if(tab==1){a.resultTime.setText("生成时间（北京时间）：2026-11-03 21:15:42");a.resultText.setText("This is a private message. 你好，世界。");}a.root.measure(View.MeasureSpec.makeMeasureSpec(786,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(1746,View.MeasureSpec.EXACTLY));a.root.layout(0,0,786,1746);android.graphics.Bitmap bmp=android.graphics.Bitmap.createBitmap(786,1746,android.graphics.Bitmap.Config.ARGB_8888);a.root.draw(new android.graphics.Canvas(bmp));try(FileOutputStream out=new FileOutputStream("work/bip_android_screen_"+tab+".png")){bmp.compress(android.graphics.Bitmap.CompressFormat.PNG,100,out);}bmp.recycle();}
        int[]pixels=new int[560*560];Arrays.fill(pixels,0xff908070);File file=new File(a.getCacheDir(),"native-test.png");Images.png(new Transport.Image(560,560,pixels),file);UriProvider.register(a,file);Transport.Image image=Images.load(a,android.net.Uri.parse("content://org.binarypasscode.test/image"));assertEquals(560,image.width);assertEquals(0xff908070,image.pixels[0]);assertEquals(0xff908070,image.pixels[image.pixels.length-1]);a.finish();
    }
    public static class UriProvider extends android.content.ContentProvider{
        static File file;static void register(Context c,File f){file=f;UriProvider p=new UriProvider();android.content.pm.ProviderInfo info=new android.content.pm.ProviderInfo();info.authority="org.binarypasscode.test";p.attachInfo(c,info);org.robolectric.shadows.ShadowContentResolver.registerProviderInternal("org.binarypasscode.test",p);}
        public boolean onCreate(){return true;}public String getType(android.net.Uri u){return "image/png";}public android.database.Cursor query(android.net.Uri u,String[]p,String s,String[]a,String o){return null;}public android.net.Uri insert(android.net.Uri u,android.content.ContentValues v){return null;}public int delete(android.net.Uri u,String s,String[]a){return 0;}public int update(android.net.Uri u,android.content.ContentValues v,String s,String[]a){return 0;}public android.os.ParcelFileDescriptor openFile(android.net.Uri u,String mode)throws FileNotFoundException{return android.os.ParcelFileDescriptor.open(file,android.os.ParcelFileDescriptor.MODE_READ_ONLY);}
    }
}
