package org.binarypasscode.image;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.math.BigInteger;
import java.util.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** Desktop-compatible envelope and five-bit character codec. No Android dependencies. */
public final class Crypto {
    static final SecureRandom RANDOM = new SecureRandom();
    static final String SYMBOLS = "+-*/=!%_:;?\"<>()[]{}";
    static final int UNITS=60000, ENVELOPE=37595;
    static final long TIME_MOD=10000000000L;
    public static final String AUTH="无法验证消息：密钥不匹配，或图片已损坏、被修改。";
    static RuntimeException error(String s){return new IllegalArgumentException(s);}
    static void check(){if(Thread.currentThread().isInterrupted())throw error("操作已取消。");}
    public static void validate(String key){if(key==null||!key.matches("[0-9]{128}"))throw error("密钥必须为128位半角数字，前导零必须保留。");}
    public static String generate(){StringBuilder b=new StringBuilder();for(int i=0;i<128;i++)b.append(RANDOM.nextInt(10));return b.toString();}
    static byte[] bytes(String s){return s.getBytes(StandardCharsets.UTF_8);}
    static byte[] random(int n){byte[] b=new byte[n];RANDOM.nextBytes(b);return b;}
    static byte[] cat(byte[]... arrays){int n=0;for(byte[] a:arrays)n+=a.length;byte[] r=new byte[n];n=0;for(byte[]a:arrays){System.arraycopy(a,0,r,n,a.length);n+=a.length;}return r;}
    static byte[] slice(byte[]a,int start,int end){return Arrays.copyOfRange(a,start,end);}
    static byte[] mac(byte[]key,byte[] data){try{Mac m=Mac.getInstance("HmacSHA256");m.init(new SecretKeySpec(key,"HmacSHA256"));return m.doFinal(data);}catch(Exception e){throw new IllegalStateException(e);}}
    static byte[] derive(String key,String purpose,byte[] nonce){validate(key);byte[] prk=mac(nonce.length==0?new byte[16]:nonce,bytes(key));return mac(prk,cat(bytes("binary_image_passcode/v2.1/"+purpose),new byte[]{1}));}
    static long read(byte[]b,int p,int n){long v=0;for(int i=0;i<n;i++)v=(v<<8)|(b[p+i]&255);return v;}
    static byte[] number(long v,int n){byte[] b=new byte[n];for(int i=n-1;i>=0;i--){b[i]=(byte)v;v>>>=8;}return b;}
    static long offset(String key,byte[]nonce){return new BigInteger(1,mac(derive(key,"time",nonce),bytes("seconds"))).mod(BigInteger.valueOf(TIME_MOD)).longValue();}
    static byte[] mask(String key,byte[]nonce,long time,int n){byte[] sub=derive(key,"body",nonce),context=cat(bytes("mask\0"),number(time,5),nonce),out=new byte[n];for(int i=0;i*32<n;i++){check();byte[]b=mac(sub,cat(context,number(i,2)));System.arraycopy(b,0,out,i*32,Math.min(32,n-i*32));}return out;}
    static int symbol(int value){int slot=10;for(int i=0;i<SYMBOLS.length();i++){while(slot==29||slot==31)slot++;if(slot==value)return i;slot++;}return -1;}
    static int symbolCode(char c){int idx=SYMBOLS.indexOf(c),slot=10;for(int i=0;i<idx;i++){slot++;while(slot==29||slot==31)slot++;}return slot;}
    static boolean basic(char c){return c>='a'&&c<='z'||c>='A'&&c<='Z'||c>='0'&&c<='9'||" .,\\|".indexOf(c)>=0||SYMBOLS.indexOf(c)>=0;}
    public static int[] units(String text){
        if(text==null||text.isEmpty())throw error("请输入正文。");
        if(text.length()>UNITS)throw error("正文最多60,000字符，编码后也不能超过60,000单元。");
        ArrayList<Integer> v=new ArrayList<>();boolean numeric=false,upper=false;
        for(int i=0;i<text.length();i++){
            char c=text.charAt(i);if(Character.isSurrogate(c))throw error("第"+(i+1)+"个字符暂不支持，请移除该表情或罕见字后重试。");
            if(c=='.'){v.add(29);continue;}
            if(c>='0'&&c<='9'||SYMBOLS.indexOf(c)>=0){if(!numeric){v.add(31);numeric=true;}v.add(c>='0'&&c<='9'?c-'0':symbolCode(c));continue;}
            if(numeric){v.add(31);numeric=false;}
            if(c==' ')v.add(28);
            else if(c==',')v.add(26);
            else if(c>='a'&&c<='z'||c>='A'&&c<='Z'){boolean need=c>='A'&&c<='Z';if(need!=upper){v.add(30);upper=need;}v.add(Character.toLowerCase(c)-'a');}
            else if(c=='|'){if(!upper){v.add(30);upper=true;}v.add(27);}
            else {if(upper){v.add(30);upper=false;}v.add(27);if(c=='\\'){if(i+1<text.length()&&text.charAt(i+1)=='u'){v.add(30);v.add(30);}}else{v.add(20);for(int s=12;s>=0;s-=4)v.add((c>>s)&15);}}
            if(v.size()>UNITS)throw error("正文编码超过60,000单元。扩展字符各占6单元，请缩短正文。");
        }
        if(numeric)v.add(31);if(v.size()>UNITS)throw error("正文编码超过60,000单元，请缩短正文。");int[] out=new int[v.size()];for(int i=0;i<out.length;i++)out[i]=v.get(i);return out;
    }
    static String decodeUnits(int[] v){StringBuilder s=new StringBuilder();boolean num=false,up=false;
        for(int i=0;i<v.length;i++){int a=v[i];if(a==29)s.append('.');else if(a==31)num=!num;
            else if(num){if(a<10)s.append((char)('0'+a));else{int si=symbol(a);if(si<0)throw error("数字编码无效。");s.append(SYMBOLS.charAt(si));}}
            else if(a==30)up=!up;else if(a==28)s.append(' ');else if(a==26)s.append(',');
            else if(a==27){if(up)s.append('|');else if(i+1<v.length&&v[i+1]==20){if(i+5>=v.length)throw error("字符编码不完整。");int cp=0;for(int j=0;j<4;j++){int d=v[i+2+j];if(d>15)throw error("字符编码无效。");cp=(cp<<4)|d;}char c=(char)cp;if(Character.isSurrogate(c)||basic(c))throw error("字符编码无效。");s.append(c);i+=5;}else s.append('\\');}
            else if(a<26)s.append((char)((up?'A':'a')+a));else throw error("字符编码无效。");
        }if(num)throw error("数字编码未闭合。");return s.toString();
    }
    public static byte[] seal(String text,String key,long seconds,byte[]nonce){
        validate(key);int[] v=units(text);if(seconds<0||seconds>=TIME_MOD||nonce.length!=48)throw error("时间或随机值无效。");
        byte[] plain=new byte[37502];plain[0]=(byte)(v.length>>8);plain[1]=(byte)v.length;
        for(int i=0;i<UNITS;i++){int value=i<v.length?v[i]:28;for(int j=0;j<5;j++){int bit=i*5+j;plain[2+bit/8]|=((value>>(4-j))&1)<<(7-bit%8);}}
        byte[] header=cat(bytes("BIP2"),new byte[]{2,1,2,0},nonce,number((seconds+offset(key,nonce))%TIME_MOD,5)),m=mask(key,nonce,seconds,plain.length);
        for(int i=0;i<plain.length;i++)plain[i]^=m[i];byte[] content=cat(header,plain);return cat(content,mac(derive(key,"authentication",nonce),content));
    }
    public static final class Message {public String text;public long seconds;public int used;Message(String t,long s,int u){text=t;seconds=s;used=u;}}
    public static Message open(byte[] data,String key){validate(key);if(data.length!=ENVELOPE)throw error(AUTH);byte[]nonce=slice(data,8,56),tag=slice(data,data.length-32,data.length),content=slice(data,0,data.length-32);
        if(!MessageDigest.isEqual(tag,mac(derive(key,"authentication",nonce),content)))throw error(AUTH);
        if(!Arrays.equals(slice(data,0,8),cat(bytes("BIP2"),new byte[]{2,1,2,0}))||read(data,56,5)>=TIME_MOD)throw error("消息格式无效。");
        long seconds=(read(data,56,5)-offset(key,nonce)+TIME_MOD)%TIME_MOD;byte[]plain=slice(data,61,data.length-32),m=mask(key,nonce,seconds,plain.length);for(int i=0;i<plain.length;i++)plain[i]^=m[i];
        int used=(int)read(plain,0,2);if(used<1||used>UNITS)throw error("正文长度无效。");int[]v=new int[used];for(int i=0;i<UNITS;i++){int val=0;for(int j=0;j<5;j++){int bit=i*5+j;val=(val<<1)|((plain[2+bit/8]>>(7-bit%8))&1);}if(i<used)v[i]=val;else if(val!=28)throw error("正文填充无效。");}return new Message(decodeUnits(v),seconds,used);
    }
}
