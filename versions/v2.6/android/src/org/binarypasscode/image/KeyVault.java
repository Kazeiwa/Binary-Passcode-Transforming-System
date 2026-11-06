package org.binarypasscode.image;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;
import org.json.*;
import java.io.*;
import java.security.KeyStore;
import java.util.*;
import javax.crypto.*;
import javax.crypto.spec.*;

/** Encrypts the complete multi-key record with a non-exportable Android Keystore key. */
final class KeyVault {
    static final String ALIAS="binary_image_passcode.vault.v1";
    final AtomicFile file;JSONObject data;
    KeyVault(Context context)throws Exception{file=new AtomicFile(new File(context.getFilesDir(),"keys.bipvault"));if(file.getBaseFile().exists()||new File(file.getBaseFile().getPath()+".bak").exists()){
        byte[]stored;try(InputStream in=file.openRead()){stored=read(in,1048576);}if(stored.length<29)throw Crypto.error("本地密钥库已损坏，请恢复密钥备份。");
        data=new JSONObject(new String(crypt(Cipher.DECRYPT_MODE,deviceKey(false),Crypto.slice(stored,0,12),Crypto.slice(stored,12,stored.length),Crypto.bytes(ALIAS)),"UTF-8"));validateData(data);
    }else{data=new JSONObject();data.put("keys",new JSONArray());data.put("default","");}}
    static byte[]read(InputStream in,int max)throws IOException{ByteArrayOutputStream out=new ByteArrayOutputStream();byte[]b=new byte[32768];int n;while((n=in.read(b))!=-1){Crypto.check();if(out.size()+n>max)throw new IOException("文件过大。");out.write(b,0,n);}return out.toByteArray();}
    static KeyVault rebuild(Context context)throws Exception{
        File original=new File(context.getFilesDir(),"keys.bipvault"),saved=new File(context.getFilesDir(),"unreadable-keys-"+System.currentTimeMillis());
        if(!saved.mkdir())throw Crypto.error("无法保留原密钥库，请检查设备剩余空间。");
        for(String suffix:new String[]{"",".bak",".new"}){File source=new File(original.getPath()+suffix);if(source.exists()&&!source.renameTo(new File(saved,"keys.bipvault"+suffix)))throw Crypto.error("无法保留原密钥库，请重启应用后重试。");}
        return new KeyVault(context);
    }
    static javax.crypto.SecretKey deviceKey(boolean create)throws Exception{KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);if(ks.containsAlias(ALIAS))return (javax.crypto.SecretKey)ks.getKey(ALIAS,null);if(!create)throw Crypto.error("本机密钥保护信息已丢失，请恢复备份。");KeyGenerator g=KeyGenerator.getInstance("AES","AndroidKeyStore");g.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setKeySize(256).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());return g.generateKey();}
    static byte[]crypt(int mode,javax.crypto.SecretKey key,byte[]iv,byte[]payload,byte[]aad)throws Exception{Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(mode,key,new GCMParameterSpec(128,iv));c.updateAAD(aad);return c.doFinal(payload);}
    static void validateData(JSONObject obj)throws Exception{JSONArray a=obj.getJSONArray("keys");if(a.length()>200)throw Crypto.error("密钥数量超过200个。");HashSet<String>ids=new HashSet<>();for(int i=0;i<a.length();i++){JSONObject r=a.getJSONObject(i);Crypto.validate(r.getString("key"));String id=r.getString("id"),name=r.getString("name");if(name.trim().isEmpty()||name.length()>80||!ids.add(id))throw Crypto.error("密钥备份无效。");}String def=obj.getString("default");if(!def.isEmpty()&&!ids.contains(def))throw Crypto.error("默认密钥无效。");}
    synchronized void save()throws Exception{validateData(data);Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,deviceKey(true));c.updateAAD(Crypto.bytes(ALIAS));byte[]payload=Crypto.cat(c.getIV(),c.doFinal(Crypto.bytes(data.toString())));FileOutputStream out=null;try{out=file.startWrite();out.write(payload);out.flush();out.getFD().sync();file.finishWrite(out);}catch(Exception e){if(out!=null)file.failWrite(out);throw e;}finally{if(out!=null)out.close();}}
    synchronized ArrayList<JSONObject> list()throws Exception{ArrayList<JSONObject>r=new ArrayList<>();JSONArray a=data.getJSONArray("keys");for(int i=0;i<a.length();i++)r.add(new JSONObject(a.getJSONObject(i).toString()));return r;}
    synchronized String defaultId(){return data.optString("default","");}
    synchronized JSONObject find(String id)throws Exception{for(JSONObject r:list())if(r.getString("id").equals(id))return r;throw Crypto.error("请选择密钥。");}
    synchronized String add(String name,String key)throws Exception{Crypto.validate(key);name=name.trim();if(name.isEmpty()||name.length()>80)throw Crypto.error("密钥名称应为1至80个字符。");for(JSONObject r:list())if(r.getString("name").equals(name))throw Crypto.error("密钥名称已存在。");String id=UUID.randomUUID().toString();JSONObject old=new JSONObject(data.toString());try{JSONObject r=new JSONObject();r.put("id",id);r.put("name",name);r.put("key",key);data.getJSONArray("keys").put(r);if(defaultId().isEmpty())data.put("default",id);save();return id;}catch(Exception e){data=old;throw e;}}
    synchronized void setDefault(String id)throws Exception{find(id);JSONObject old=new JSONObject(data.toString());try{data.put("default",id);save();}catch(Exception e){data=old;throw e;}}
    synchronized void rename(String id,String name)throws Exception{name=name.trim();if(name.isEmpty()||name.length()>80)throw Crypto.error("名称应为1至80个字符。");for(JSONObject r:list())if(r.getString("name").equals(name)&&!r.getString("id").equals(id))throw Crypto.error("密钥名称已存在。");JSONObject old=new JSONObject(data.toString());try{JSONArray a=data.getJSONArray("keys");for(int i=0;i<a.length();i++)if(a.getJSONObject(i).getString("id").equals(id))a.getJSONObject(i).put("name",name);save();}catch(Exception e){data=old;throw e;}}
    synchronized void delete(String id)throws Exception{find(id);JSONObject old=new JSONObject(data.toString());try{JSONArray a=data.getJSONArray("keys"),next=new JSONArray();for(int i=0;i<a.length();i++)if(!a.getJSONObject(i).getString("id").equals(id))next.put(a.getJSONObject(i));data.put("keys",next);if(defaultId().equals(id))data.put("default",next.length()==0?"":next.getJSONObject(0).getString("id"));save();}catch(Exception e){data=old;throw e;}}
    static javax.crypto.SecretKey backupKey(char[]password,byte[]salt)throws Exception{if(password.length<12)throw Crypto.error("备份密码至少12个字符。");PBEKeySpec spec=new PBEKeySpec(password,salt,210000,256);try{return new SecretKeySpec(SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded(),"AES");}finally{spec.clearPassword();}}
    synchronized byte[] backup(char[]password)throws Exception{byte[]salt=Crypto.random(16),iv=Crypto.random(12),prefix=Crypto.cat(Crypto.bytes("BIPAK1"),salt,iv);return Crypto.cat(prefix,crypt(Cipher.ENCRYPT_MODE,backupKey(password,salt),iv,Crypto.bytes(data.toString()),prefix));}
    synchronized int restore(byte[]stored,char[]password)throws Exception{if(stored.length<50||stored.length>1048576||!Arrays.equals(Crypto.slice(stored,0,6),Crypto.bytes("BIPAK1")))throw Crypto.error("不是有效的密钥备份文件。");JSONObject imported;try{byte[]plain=crypt(Cipher.DECRYPT_MODE,backupKey(password,Crypto.slice(stored,6,22)),Crypto.slice(stored,22,34),Crypto.slice(stored,34,stored.length),Crypto.slice(stored,0,34));imported=new JSONObject(new String(plain,"UTF-8"));validateData(imported);}catch(Exception e){throw Crypto.error("备份密码不正确，或文件已损坏。");}JSONObject old=new JSONObject(data.toString());int added=0;try{JSONArray incoming=imported.getJSONArray("keys");for(int i=0;i<incoming.length();i++){JSONObject r=incoming.getJSONObject(i);boolean exists=false;for(JSONObject mine:list())if(mine.getString("key").equals(r.getString("key")))exists=true;if(exists)continue;String name=r.getString("name"),base=name;int suffix=2;boolean collision=true;while(collision){collision=false;for(JSONObject mine:list())if(mine.getString("name").equals(name)){collision=true;name=base.substring(0,Math.min(base.length(),65))+" ("+(suffix++)+")";break;}}JSONObject record=new JSONObject();String id=UUID.randomUUID().toString();record.put("id",id);record.put("name",name);record.put("key",r.getString("key"));data.getJSONArray("keys").put(record);if(defaultId().isEmpty())data.put("default",id);added++;}Crypto.check();save();return added;}catch(Exception e){data=old;throw e;}}
}
