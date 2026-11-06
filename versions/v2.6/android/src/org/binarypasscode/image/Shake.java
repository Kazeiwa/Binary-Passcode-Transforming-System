package org.binarypasscode.image;

/** SHAKE256 (FIPS 202), used only for the format's deterministic slot permutation. */
final class Shake {
    static final long[] RC={0x1L,0x8082L,0x800000000000808aL,0x8000000080008000L,0x808bL,0x80000001L,0x8000000080008081L,0x8000000000008009L,0x8aL,0x88L,0x80008009L,0x8000000aL,0x8000808bL,0x800000000000008bL,0x8000000000008089L,0x8000000000008003L,0x8000000000008002L,0x8000000000000080L,0x800aL,0x800000008000000aL,0x8000000080008081L,0x8000000000008080L,0x80000001L,0x8000000080008008L};
    static final int[] ROT={0,1,62,28,27,36,44,6,55,20,3,10,43,25,39,41,45,15,21,8,18,2,61,56,14};
    static void perm(long[]a){long[]c=new long[5],b=new long[25];for(long rc:RC){for(int x=0;x<5;x++)c[x]=a[x]^a[x+5]^a[x+10]^a[x+15]^a[x+20];for(int x=0;x<5;x++){long d=c[(x+4)%5]^Long.rotateLeft(c[(x+1)%5],1);for(int y=0;y<5;y++)a[x+5*y]^=d;}for(int x=0;x<5;x++)for(int y=0;y<5;y++)b[y+5*((2*x+3*y)%5)]=Long.rotateLeft(a[x+5*y],ROT[x+5*y]);for(int x=0;x<5;x++)for(int y=0;y<5;y++)a[x+5*y]=b[x+5*y]^((~b[(x+1)%5+5*y])&b[(x+2)%5+5*y]);a[0]^=rc;}}
    static byte[] digest(byte[]input,int length){long[]a=new long[25];int p=0;for(byte v:input){a[p/8]^=(v&255L)<<(8*(p%8));if(++p==136){perm(a);p=0;}}a[p/8]^=31L<<(8*(p%8));a[16]^=0x8000000000000000L;perm(a);byte[]out=new byte[length];p=0;for(int i=0;i<length;i++){if(p==136){perm(a);p=0;}out[i]=(byte)(a[p/8]>>>(8*(p%8)));p++;}return out;}
}
