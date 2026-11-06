package org.binarypasscode.image;

import java.util.*;
import java.security.MessageDigest;

/** Cross-platform RGB parity transport. Coordinates remain recoverable after cropping. */
public final class Transport {
    public interface Progress {void update(int percent,String text);}
    public static final class Image {
        public final int width,height;public final int[] pixels;final Image source;final int rotation;
        public Image(int w,int h,int[]p){width=w;height=h;pixels=p;source=null;rotation=0;if((long)w*h!=p.length)throw Crypto.error("图片数据无效。");}
        Image(Image s,int r){source=s;rotation=r;pixels=s.pixels;width=r%2==0?s.width:s.height;height=r%2==0?s.height:s.width;}
        int get(int x,int y){if(source==null)return pixels[y*width+x];if(rotation==1)return source.get(source.width-1-y,x);if(rotation==2)return source.get(source.width-1-x,source.height-1-y);return source.get(y,source.height-1-x);}
        int bit(int x,int y,int channel){return (get(x,y)>>(16-8*channel))&1;}
        void bit(int x,int y,int c,int b){int p=y*width+x,shift=16-8*c;pixels[p]=(pixels[p]&~(1<<shift))|(b<<shift);}
    }
    public static final class Layout {public int n,k,size,mx,my;public double margin,fraction;public int[][]origins;}
    public static final class Result {public Crypto.Message message;public int recovered,total,required,corrected,rotation;}
    static final int[][] FINDERS={{8,8},{106,8},{8,106}};
    static final int[] AVAILABLE=available();
    static int[] available(){ArrayList<Integer>a=new ArrayList<>();for(int y=0;y<128;y++)for(int x=0;x<128;x++)for(int c=0;c<3;c++){boolean excluded=false;if(c==0)for(int[]p:FINDERS)if(x>=p[0]-2&&x<p[0]+16&&y>=p[1]-2&&y<p[1]+16)excluded=true;if(!excluded)a.add((y*128+x)*3+c);}int[]out=new int[a.size()];for(int i=0;i<out.length;i++)out[i]=a.get(i);return out;}
    static int coded(int n){return n+32*((n+222)/223);}
    public static Layout layout(int w,int h,boolean strong){
        if(w<=0||h<=0||(long)w*h>80000000||Math.max(w,h)>20000)throw Crypto.error("图片最多支持8,000万像素，单边不超过20,000。");
        long min=strong?484416:313600;if((long)w*h<min||Math.min(w,h)<140)throw Crypto.error("图片过小。"+(strong?"增强模式至少484,416像素（方图参考696×696）。":"均衡模式至少313,600像素（方图参考560×560）。")+"短边至少140像素，推荐1024×1024及以上。");
        Layout l=new Layout();l.margin=Math.min(.12,.04+.02*Math.log(Math.max(1.,(double)w*h/1048576))/Math.log(2));l.mx=(int)Math.ceil(w*l.margin);l.my=(int)Math.ceil(h*l.margin);int mc=(w-2*l.mx)/128,mr=(h-2*l.my)/128,cols=mc,rows=mr;
        if(mc<1||mr<1)throw Crypto.error("图片太窄，请选择宽一些的图片。");
        if(mc*mr>196){int best=0;double score=Double.POSITIVE_INFINITY;for(int c=1;c<=Math.min(mc,196);c++){int r=Math.min(mr,196/c),n=c*r;double s=Math.abs(Math.log(((double)c/r)/((double)w/h)));if(n>best||n==best&&s<score){cols=c;rows=r;best=n;score=s;}}}
        l.n=cols*rows;l.k=(l.n+(strong?2:1))/(strong?3:2);l.size=(Crypto.ENVELOPE+l.k-1)/l.k;int bits=784+coded(l.size+16)*8;
        if(l.k<8||bits>AVAILABLE.length)throw Crypto.error("当前图片长宽比无法容纳消息，请选择更大或更接近方形的图片。");
        l.origins=new int[l.n][2];int idx=0;for(int y=0;y<rows;y++)for(int x=0;x<cols;x++){l.origins[idx][0]=(int)Math.rint(cols==1?l.mx:l.mx+(double)x*(w-2*l.mx-128)/(cols-1));l.origins[idx++][1]=(int)Math.rint(rows==1?l.my:l.my+(double)y*(h-2*l.my-128)/(rows-1));}l.fraction=(double)l.n*(bits+972)/((double)w*h*3);return l;
    }
    static int compare(int a,int b,long[]keys){int c=Long.compareUnsigned(keys[a],keys[b]);return c==0?Integer.compare(a,b):c;}
    static void sort(int[]a,int lo,int hi,long[]keys){while(lo<hi){int i=lo,j=hi,p=a[(lo+hi)>>>1];while(i<=j){while(compare(a[i],p,keys)<0)i++;while(compare(a[j],p,keys)>0)j--;if(i<=j){int t=a[i];a[i++]=a[j];a[j--]=t;}}if(j-lo<hi-i){if(lo<j)sort(a,lo,j,keys);lo=i;}else{if(i<hi)sort(a,i,hi,keys);hi=j;}}}
    static int[] permutation(int[]pool,byte[]seed){Crypto.check();byte[]words=Shake.digest(Crypto.cat(Crypto.bytes("BIP/positions/v2.1\0"),seed),pool.length*8);long[]keys=new long[pool.length];int[]indices=new int[pool.length];for(int i=0;i<keys.length;i++){keys[i]=Crypto.read(words,i*8,8);indices[i]=i;}sort(indices,0,indices.length-1,keys);int[]out=new int[pool.length];for(int i=0;i<out.length;i++)out[i]=pool[indices[i]];return out;}
    static int[][] headerPositions(String key){int[]order=permutation(AVAILABLE,Crypto.derive(key,"header-positions",new byte[0]));return new int[][]{Arrays.copyOf(order,784),Arrays.copyOfRange(order,784,order.length)};}
    static int[] bodyPositions(int[]pool,byte[]sub,int index){return permutation(pool,Crypto.mac(sub,new byte[]{(byte)index}));}
    static void write(Image image,int x,int y,int[]positions,byte[]data){for(int bit=0;bit<data.length*8;bit++){int slot=positions[bit],pixel=slot/3;image.bit(x+pixel%128,y+pixel/128,slot%3,(data[bit/8]>>(7-bit%8))&1);}}
    static byte[] read(Image image,int x,int y,int[]positions,int length){byte[]data=new byte[length];for(int bit=0;bit<length*8;bit++){int slot=positions[bit],pixel=slot/3;data[bit/8]|=image.bit(x+pixel%128,y+pixel/128,slot%3)<<(7-bit%8);}return data;}
    static int finder(int x,int y){return x<2||x>=12||y<2||y>=12||x>=4&&x<10&&y>=4&&y<10?1:0;}
    static void paint(Image image,int x,int y){for(int[]p:FINDERS)for(int dy=-2;dy<16;dy++)for(int dx=-2;dx<16;dx++)image.bit(x+p[0]+dx,y+p[1]+dy,0,dx>=0&&dx<14&&dy>=0&&dy<14?finder(dx,dy):0);}
    static byte[] header(byte[]nonce,int i,Layout l){return Crypto.cat(Crypto.bytes("BIPT"),new byte[]{2,2,1,0},nonce,new byte[]{(byte)i,(byte)l.k,(byte)l.n,0},Crypto.number(l.size,2),Crypto.number(Crypto.ENVELOPE,4));}
    public static Layout encode(Image image,String text,String key,boolean strong,Progress progress){
        Crypto.validate(key);Layout l=layout(image.width,image.height,strong);byte[]env=Crypto.seal(text,key,System.currentTimeMillis()/1000,Crypto.random(48)),nonce=Crypto.slice(env,8,56);if(progress!=null)progress.update(2,"正在准备图片…");byte[][]shards=Codes.encode(env,l.n,l.k);int[][]pos=headerPositions(key);byte[]auth=Crypto.derive(key,"packet-authentication",nonce),positionKey=Crypto.derive(key,"body-positions",nonce);
        for(int i=0;i<l.n;i++){Crypto.check();int x=l.origins[i][0],y=l.origins[i][1];byte[]h=header(nonce,i,l),tag=Arrays.copyOf(Crypto.mac(auth,Crypto.cat(h,shards[i])),16);paint(image,x,y);write(image,x,y,pos[0],Codes.rsEncode(h));write(image,x,y,bodyPositions(pos[1],positionKey,i),Codes.rsEncode(Crypto.cat(shards[i],tag)));if(progress!=null)progress.update(5+90*(i+1)/l.n,"正在写入图片 "+(i+1)+"/"+l.n);}
        return l;
    }
    static long point(int x,int y){return ((long)y<<32)|(x&0xffffffffL);}
    static int sum(int[]a,int stride,int x,int y,int size){return a[(y+size)*stride+x+size]-a[y*stride+x+size]-a[(y+size)*stride+x]+a[y*stride+x];}
    static List<int[]> locate(Image image){int w=image.width,h=image.height;HashSet<Long>points=new HashSet<>();if(w<128||h<128)return new ArrayList<>();
        for(int start=0;start<h-13;start+=256){Crypto.check();int oh=Math.min(256,h-13-start),rows=oh+13,stride=w+1;int[]integ=new int[(rows+1)*stride];for(int y=0;y<rows;y++){int line=0;for(int x=0;x<w;x++){line+=image.bit(x,y+start,0);integ[(y+1)*stride+x+1]=integ[y*stride+x+1]+line;}}
            for(int y=0;y<oh;y++)for(int x=0;x<w-13;x++){int mismatch=132-sum(integ,stride,x,y,14)+2*sum(integ,stride,x+2,y+2,10)-2*sum(integ,stride,x+4,y+4,6);if(mismatch<=12){points.add(point(x,y+start));if(points.size()>6000)throw Crypto.error("定位标记过多，无法识别此图片。");}}
        }
        ArrayList<int[]>origins=new ArrayList<>();for(long p:points){int x=(int)p-8,y=(int)(p>>>32)-8;if(x>=0&&y>=0&&x+128<=w&&y+128<=h&&points.contains(point(x+106,y+8))&&points.contains(point(x+8,y+106)))origins.add(new int[]{x,y});}Collections.sort(origins,(a,b)->a[1]!=b[1]?Integer.compare(a[1],b[1]):Integer.compare(a[0],b[0]));return origins;
    }
    static final class Group {byte[]nonce;int k,n,size,errors,rotation;TreeMap<Integer,byte[]>shards=new TreeMap<>();}
    public static Result decode(Image image,String key,Progress progress){Crypto.validate(key);int[][]pos=headerPositions(key);HashMap<String,Group>groups=new HashMap<>();int markers=0;
        for(int rotation=0;rotation<4;rotation++){Crypto.check();Image current=rotation==0?image:new Image(image,rotation);if(progress!=null)progress.update(rotation*25,"正在定位图片，方向 "+(rotation+1)+"/4");List<int[]>origins=locate(current);markers+=origins.size();int j=0;
            for(int[]origin:origins){Crypto.check();try{
                byte[]h=Codes.rsDecode(read(current,origin[0],origin[1],pos[0],98));int errors=Codes.corrected;
                if(h.length!=66||!Arrays.equals(Crypto.slice(h,0,8),Crypto.cat(Crypto.bytes("BIPT"),new byte[]{2,2,1,0}))||h[59]!=0)continue;
                int index=h[56]&255,k=h[57]&255,n=h[58]&255,size=(int)Crypto.read(h,60,2);if(k<8||k>n||n>196||index>=n||Crypto.read(h,62,4)!=Crypto.ENVELOPE||size!=(Crypto.ENVELOPE+k-1)/k||coded(size+16)*8>pos[1].length)continue;
                byte[]nonce=Crypto.slice(h,8,56),sub=Crypto.derive(key,"body-positions",nonce),body=Codes.rsDecode(read(current,origin[0],origin[1],bodyPositions(pos[1],sub,index),coded(size+16)));errors+=Codes.corrected;if(body.length!=size+16)continue;
                byte[]shard=Crypto.slice(body,0,size),tag=Crypto.slice(body,size,body.length),expected=Arrays.copyOf(Crypto.mac(Crypto.derive(key,"packet-authentication",nonce),Crypto.cat(h,shard)),16);if(!MessageDigest.isEqual(tag,expected))continue;
                String id=Base64.getEncoder().encodeToString(nonce)+":"+k+":"+n;Group g=groups.get(id);if(g==null){if(groups.size()>=32)throw Crypto.error("图片包含过多不同消息。");g=new Group();g.nonce=nonce;g.k=k;g.n=n;g.size=size;g.rotation=rotation;groups.put(id,g);}if(!g.shards.containsKey(index)){g.shards.put(index,shard);g.errors+=errors;}
            }catch(IllegalArgumentException e){/* Corrupted or unrelated candidate: try the remaining authenticated blocks. */}
                if(progress!=null)progress.update(rotation*25+25*(++j)/Math.max(1,origins.size()),"正在校验图片 "+j+"/"+origins.size());
            }
            for(Group g:groups.values())if(g.shards.size()>=g.k){byte[]env=Codes.decode(g.shards,g.n,g.k,Crypto.ENVELOPE);if(!MessageDigest.isEqual(Crypto.slice(env,8,56),g.nonce))throw Crypto.error(Crypto.AUTH);Result r=new Result();r.message=Crypto.open(env,key);r.recovered=g.shards.size();r.total=g.n;r.required=g.k;r.corrected=g.errors;r.rotation=g.rotation*90;return r;}
        }
        if(!groups.isEmpty()){Group best=Collections.max(groups.values(),(a,b)->Double.compare((double)a.shards.size()/a.k,(double)b.shards.size()/b.k));throw Crypto.error("可读数据块不足：找到"+best.shards.size()+"/"+best.n+"块，至少需要"+best.k+"块。图片可能被过度裁剪或修改。");}
        throw Crypto.error(markers>0?Crypto.AUTH:"未找到可识别的消息。请使用原始PNG，确认图片没有被缩放、截图或压缩为JPG。");
    }
}
