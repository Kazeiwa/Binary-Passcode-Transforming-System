package org.binarypasscode.image;

import java.nio.file.*;
import java.util.*;
import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;

public class CoreTest {
    static void require(boolean b){if(!b)throw new AssertionError();}
    static String hex(byte[]data){StringBuilder b=new StringBuilder();for(byte v:data)b.append(String.format("%02x",v&255));return b.toString();}
    static Transport.Image load(String path)throws Exception {BufferedImage b=ImageIO.read(Paths.get(path).toFile());return new Transport.Image(b.getWidth(),b.getHeight(),b.getRGB(0,0,b.getWidth(),b.getHeight(),null,0,b.getWidth()));}
    public static void main(String[]a)throws Exception {
        String key="01234567";while(key.length()<128)key+=key;if(a.length>3)key=a[3];String text="Hello, 世界 日本語 한글. 0123456789 +-*/=!%_:;?\"<>()[]{} | \\u \\ @#$^&’\n";
        if(a.length>0){Transport.Image image=load(a[1]);if(a[0].equals("decode")){Transport.Result r=Transport.decode(image,key,null);Files.write(Paths.get(a[2]),Crypto.bytes(r.message.text));System.out.println("DECODE "+r.recovered+"/"+r.total+" corrected="+r.corrected);}
            else{Transport.Layout l=Transport.encode(image,text,key,a[0].equals("strong"),null);BufferedImage out=new BufferedImage(image.width,image.height,BufferedImage.TYPE_INT_RGB);out.setRGB(0,0,image.width,image.height,image.pixels,0,image.width);ImageIO.write(out,"png",Paths.get(a[2]).toFile());System.out.println("ENCODE "+l.n+"/"+l.k);}return;}
        require(hex(Shake.digest(new byte[0],64)).equals("46b9dd2b0ba88d13233b3feb743eeb243fcd52ea62b81b82b50c27646ed5762fd75dc4ddd8c0f200cb05019d67b592f6fc821c49479ab48640292eacb3b7c4be"));
        byte[]nonce=new byte[48];for(int i=0;i<48;i++)nonce[i]=(byte)i;byte[]env=Crypto.seal(text,key,1793701842L,nonce);require(Crypto.open(env,key).text.equals(text));Files.write(Paths.get("work/bip_android_envelope.bin"),env);
        Random random=new Random(93);
        for(int n:new int[]{1,66,223,224,1024,4716}){byte[]data=new byte[n];random.nextBytes(data);byte[]encoded=Codes.rsEncode(data);require(Arrays.equals(data,Codes.rsDecode(encoded)));for(int start=0;start<encoded.length;start+=255){int len=Math.min(255,encoded.length-start);HashSet<Integer>positions=new HashSet<>();while(positions.size()<Math.min(16,len))positions.add(random.nextInt(len));for(int p:positions)encoded[start+p]^=(byte)(1+random.nextInt(255));}require(Arrays.equals(data,Codes.rsDecode(encoded)));}
        byte[]data=new byte[37595];random.nextBytes(data);byte[][]shards=Codes.encode(data,24,8);TreeMap<Integer,byte[]>selected=new TreeMap<>();for(int i=8;i<16;i++)selected.put(i,shards[i]);require(Arrays.equals(data,Codes.decode(selected,24,8,data.length)));
        StringBuilder all=new StringBuilder();for(int c=0;c<=65535;c++)if(!Character.isSurrogate((char)c))all.append((char)c);for(int i=0;i<all.length();i+=4000){String t=all.substring(i,Math.min(i+4000,all.length()));require(t.equals(Crypto.decodeUnits(Crypto.units(t))));}
        String full=String.join("",Collections.nCopies(60000,"a"));require(Crypto.open(Crypto.seal(full,key,9999999999L,nonce),key).text.equals(full));
        boolean rejected=false;env[100]^=1;try{Crypto.open(env,key);}catch(IllegalArgumentException e){rejected=true;}require(rejected);
        System.out.println("PASS SHAKE256, full BMP codec, 60000-unit limit, time boundary, authentication, RS 16-byte correction, outer erasure recovery");
    }
}
