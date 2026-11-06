package org.binarypasscode.image;

import java.math.BigInteger;
import java.util.*;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** V2.5/2.6 image envelope, byte-compatible with the Windows implementation. */
public final class ImagePayload {
    static final int MAX_JPEG=512000,MAX_PNG=9000000,OVERHEAD=87;
    public static final class Prepared {
        public final byte[] data;public final int width,height,quality,originalWidth,originalHeight;public final boolean png;
        public Prepared(byte[]d,int w,int h,int q,boolean p,int ow,int oh){data=d;width=w;height=h;quality=q;png=p;originalWidth=ow;originalHeight=oh;}
    }
    static byte[] derive(String key,String purpose,byte[]nonce){Crypto.validate(key);return Crypto.mac(Crypto.mac(nonce,Crypto.bytes(key)),Crypto.cat(Crypto.bytes("binary_image_passcode/v2.5/"+purpose),new byte[]{1}));}
    static long offset(String key,byte[]nonce){return new BigInteger(1,Crypto.mac(derive(key,"image-time",nonce),Crypto.bytes("seconds"))).mod(BigInteger.valueOf(Crypto.TIME_MOD)).longValue();}
    static byte[] iv(String key,byte[]nonce){return Arrays.copyOf(Crypto.mac(derive(key,"image-iv",nonce),Crypto.bytes("jpeg")),12);}
    static void validate(Prepared p){
        if(p.width<1||p.height<1||Math.max(p.width,p.height)>1920||Math.min(p.width,p.height)>1080||p.data.length<1||p.data.length>(p.png?MAX_PNG:MAX_JPEG)||(p.png?p.quality!=0:p.quality<50||p.quality>85))throw Crypto.error("图片正文尺寸或参数无效。");
        byte[]d=p.data;
        if(p.png){if(d.length<33||!Arrays.equals(Arrays.copyOf(d,8),new byte[]{(byte)137,80,78,71,13,10,26,10})||Crypto.read(d,16,4)!=p.width||Crypto.read(d,20,4)!=p.height||d[24]!=8||(d[25]!=2&&d[25]!=6))throw Crypto.error("PNG图片正文无效。");}
        else {boolean found=false;if(d.length<4||(d[0]&255)!=255||(d[1]&255)!=216)throw Crypto.error("JPG图片正文无效。");int i=2;while(i+3<d.length){if((d[i++]&255)!=255)throw Crypto.error("JPG结构无效。");while(i<d.length&&(d[i]&255)==255)i++;if(i>=d.length)break;int m=d[i++]&255;if(m==0xda||m==0xd9)break;if(m==0xd8||m==1||m>=0xd0&&m<=0xd7)continue;int length=(int)Crypto.read(d,i,2);if(length<2||i+length>d.length)throw Crypto.error("JPG图片正文不完整。");if(m>=0xc0&&m<=0xcf&&m!=0xc4&&m!=0xc8&&m!=0xcc){if(length<8||d[i+2]!=8||Crypto.read(d,i+3,2)!=p.height||Crypto.read(d,i+5,2)!=p.width||d[i+7]!=3)throw Crypto.error("JPG图片尺寸或颜色无效。");found=true;break;}i+=length;}if(!found)throw Crypto.error("JPG图片正文无效。");}
    }
    static byte[] crypt(int mode,byte[]data,String key,byte[]nonce,byte[]header){try{Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(mode,new SecretKeySpec(derive(key,"image-body",nonce),"AES"),new GCMParameterSpec(128,iv(key,nonce)));c.updateAAD(header);return c.doFinal(data);}catch(Exception e){throw Crypto.error(Crypto.AUTH);}}
    public static byte[] seal(Prepared image,String key,long seconds,byte[]nonce){Crypto.validate(key);validate(image);if(nonce.length!=48||seconds<0||seconds>=Crypto.TIME_MOD)throw Crypto.error("时间或随机值无效。");byte[]header=Crypto.cat(Crypto.bytes("BIP3"),new byte[]{3,2,3,0},nonce,Crypto.number((seconds+offset(key,nonce))%Crypto.TIME_MOD,5));byte[]plain=Crypto.cat(Crypto.number(image.width,2),Crypto.number(image.height,2),new byte[]{(byte)image.quality,(byte)(image.png?2:1)},Crypto.number(image.data.length,4),image.data);return Crypto.cat(header,crypt(Cipher.ENCRYPT_MODE,plain,key,nonce,header));}
    public static Transport.Result open(byte[]envelope,String key){Crypto.validate(key);if(envelope.length<=OVERHEAD||envelope.length>MAX_PNG+OVERHEAD)throw Crypto.error(Crypto.AUTH);byte[]nonce=Crypto.slice(envelope,8,56),header=Crypto.slice(envelope,0,61),plain=crypt(Cipher.DECRYPT_MODE,Crypto.slice(envelope,61,envelope.length),key,nonce,header);if(!Arrays.equals(Arrays.copyOf(header,8),Crypto.cat(Crypto.bytes("BIP3"),new byte[]{3,2,3,0}))||Crypto.read(header,56,5)>=Crypto.TIME_MOD||plain.length<10)throw Crypto.error("图片消息格式无效。");int kind=plain[5]&255;if(kind!=1&&kind!=2||Crypto.read(plain,6,4)!=plain.length-10)throw Crypto.error("图片消息长度无效。");Prepared p=new Prepared(Crypto.slice(plain,10,plain.length),(int)Crypto.read(plain,0,2),(int)Crypto.read(plain,2,2),plain[4]&255,kind==2,0,0);validate(p);long seconds=(Crypto.read(header,56,5)-offset(key,nonce)+Crypto.TIME_MOD)%Crypto.TIME_MOD;Transport.Result result=new Transport.Result();result.message=new Crypto.Message("",seconds,0);result.image=p;return result;}
    public static int jpegCapacity(int w,int h,boolean strong){Transport.Layout l=Transport.layout(w,h,strong,OVERHEAD+1);return Math.min(MAX_JPEG,l.k*5140-OVERHEAD);}
}
