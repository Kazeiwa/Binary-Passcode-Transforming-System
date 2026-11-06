package org.binarypasscode.image;

import java.util.*;

/** GF(256) outer erasure code and RS(255,223) inner error correction. */
final class Codes {
    static final int[] EXP=new int[510],LOG=new int[256];
    static{int a=1;for(int i=0;i<255;i++){EXP[i]=a;LOG[a]=i;a<<=1;if(a>255)a^=0x11d;}for(int i=255;i<510;i++)EXP[i]=EXP[i-255];}
    static int mul(int a,int b){return a==0||b==0?0:EXP[LOG[a]+LOG[b]];}
    static int inv(int a){if(a==0)throw Crypto.error("纠错数据无效。");return EXP[255-LOG[a]];}
    static int[][] inverse(int[][]src){int n=src.length;int[][]a=new int[n][n],o=new int[n][n];for(int i=0;i<n;i++){a[i]=src[i].clone();o[i][i]=1;}for(int c=0;c<n;c++){int pivot=c;while(pivot<n&&a[pivot][c]==0)pivot++;if(pivot==n)throw Crypto.error("恢复矩阵无效。");int[]t=a[c];a[c]=a[pivot];a[pivot]=t;t=o[c];o[c]=o[pivot];o[pivot]=t;int scale=inv(a[c][c]);for(int j=0;j<n;j++){a[c][j]=mul(a[c][j],scale);o[c][j]=mul(o[c][j],scale);}for(int r=0;r<n;r++)if(r!=c){int f=a[r][c];if(f!=0)for(int j=0;j<n;j++){a[r][j]^=mul(f,a[c][j]);o[r][j]^=mul(f,o[c][j]);}}}return o;}
    static int[][] generator(int n,int k){int[][]v=new int[n][k];for(int i=0;i<n;i++){v[i][0]=1;for(int j=1;j<k;j++)v[i][j]=mul(v[i][j-1],i+1);}int[][]top=new int[k][];System.arraycopy(v,0,top,0,k);int[][]inv=inverse(top),out=new int[n][k];for(int i=0;i<n;i++)for(int j=0;j<k;j++)for(int c=0;c<k;c++)out[i][j]^=mul(v[i][c],inv[c][j]);return out;}
    static byte[][] mat(int[][]a,byte[][]b){byte[][]out=new byte[a.length][b[0].length];for(int i=0;i<a.length;i++){Crypto.check();for(int c=0;c<b.length;c++)if(a[i][c]!=0)for(int j=0;j<b[0].length;j++)out[i][j]^=(byte)mul(a[i][c],b[c][j]&255);}return out;}
    static byte[][] encode(byte[]data,int n,int k){int size=(data.length+k-1)/k;byte[]pad=Crypto.cat(data,Crypto.random(k*size-data.length));byte[][]source=new byte[k][size];for(int i=0;i<k;i++)System.arraycopy(pad,i*size,source[i],0,size);return mat(generator(n,k),source);}
    static byte[] decode(TreeMap<Integer,byte[]>shards,int n,int k,int length){int[][]g=generator(n,k),sel=new int[k][];byte[][]src=new byte[k][];int i=0;for(Map.Entry<Integer,byte[]>e:shards.entrySet()){sel[i]=g[e.getKey()];src[i]=e.getValue();if(++i==k)break;}if(i<k)throw Crypto.error("可读数据块不足，图片可能被过度裁剪。");byte[][]rest=mat(inverse(sel),src);byte[]out=new byte[length];for(i=0;i<k;i++)System.arraycopy(rest[i],0,out,i*rest[i].length,Math.min(rest[i].length,length-i*rest[i].length));return out;}
    static final int[] GEN=gen();
    static int[] gen(){int[]g={1};for(int i=0;i<32;i++){int[]r=new int[g.length+1];for(int j=0;j<g.length;j++){r[j]^=g[j];r[j+1]^=mul(g[j],EXP[i]);}g=r;}return g;}
    static byte[] rsEncode(byte[]data){java.io.ByteArrayOutputStream all=new java.io.ByteArrayOutputStream();for(int start=0;start<data.length;start+=223){int len=Math.min(223,data.length-start);int[]r=new int[len+32];for(int i=0;i<len;i++)r[i]=data[start+i]&255;for(int i=0;i<len;i++){int f=r[i];if(f!=0)for(int j=1;j<GEN.length;j++)r[i+j]^=mul(GEN[j],f);}all.write(data,start,len);for(int i=len;i<r.length;i++)all.write(r[i]);}return all.toByteArray();}
    static int eval(int[]p,int x){int out=0;for(int a:p)out=mul(out,x)^a;return out;}
    static int[] synd(int[]r){int[]s=new int[32];for(int i=0;i<32;i++)s[i]=eval(r,EXP[i]);return s;}
    static boolean zero(int[]s){for(int v:s)if(v!=0)return false;return true;}
    static int corrected;
    static byte[] rsDecode(byte[]data){java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream();corrected=0;for(int start=0;start<data.length;start+=255){int len=Math.min(255,data.length-start);if(len<=32)throw Crypto.error("数据块损坏。");int[]r=new int[len];for(int i=0;i<len;i++)r[i]=data[start+i]&255;int[]s=synd(r);if(!zero(s)){
        // Berlekamp-Massey, ascending locator coefficients.
        int[]c=new int[33],b=new int[33];c[0]=b[0]=1;int degree=0,m=1,old=1;
        for(int t=0;t<32;t++){int d=s[t];for(int j=1;j<=degree;j++)d^=mul(c[j],s[t-j]);if(d==0){m++;continue;}int[]saved=c.clone();int scale=mul(d,inv(old));for(int j=0;j+m<c.length;j++)c[j+m]^=mul(scale,b[j]);if(2*degree<=t){degree=t+1-degree;b=saved;old=d;m=1;}else m++;}
        if(degree<1||degree>16)throw Crypto.error("数据块损坏，超出纠错范围。");int[]pos=new int[degree];int found=0;
        for(int p=0;p<len;p++){int x=EXP[(255-(len-1-p))%255],v=0;for(int j=degree;j>=0;j--)v=mul(v,x)^c[j];if(v==0){if(found==degree)throw Crypto.error("纠错失败。");pos[found++]=p;}}
        if(found!=degree)throw Crypto.error("纠错失败。");int[][]a=new int[degree][degree];for(int row=0;row<degree;row++)for(int j=0;j<degree;j++)a[row][j]=EXP[(row*(len-1-pos[j]))%255];int[][]inv=inverse(a);for(int j=0;j<degree;j++){int magnitude=0;for(int row=0;row<degree;row++)magnitude^=mul(inv[j][row],s[row]);r[pos[j]]^=magnitude;}if(!zero(synd(r)))throw Crypto.error("纠错失败。");corrected+=degree;
        }for(int i=0;i<len-32;i++)out.write(r[i]);}return out.toByteArray();}
}
