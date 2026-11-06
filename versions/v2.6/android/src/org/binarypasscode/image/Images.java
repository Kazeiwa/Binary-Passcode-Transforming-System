package org.binarypasscode.image;

import android.content.Context;
import android.graphics.*;
import android.media.ExifInterface;
import android.net.Uri;
import java.io.*;
import java.util.zip.*;

final class Images {
    static final long FILE_LIMIT=150L*1024*1024;
    static InputStream stream(Context c,Uri u)throws IOException{InputStream in=c.getContentResolver().openInputStream(u);if(in==null)throw new IOException("无法打开图片。");return new FilterInputStream(in){long count;public int read(byte[]b,int off,int len)throws IOException{int n=super.read(b,off,len);if(n>0&&(count+=n)>FILE_LIMIT)throw new IOException("图片文件超过150MB。");return n;}public int read()throws IOException{int n=super.read();if(n>=0&&++count>FILE_LIMIT)throw new IOException("图片文件超过150MB。");return n;}};}
    static int[]bounds(Context c,Uri u)throws Exception{BitmapFactory.Options opt=new BitmapFactory.Options();opt.inJustDecodeBounds=true;try(InputStream in=stream(c,u)){BitmapFactory.decodeStream(in,null,opt);}int w=opt.outWidth,h=opt.outHeight;if(w<1||h<1)throw Crypto.error("无法读取图片，请选择静态PNG、JPG、BMP或WebP。");if("image/gif".equals(opt.outMimeType))throw Crypto.error("请先将GIF导出为静态PNG图片。");if((long)w*h>80000000||Math.max(w,h)>20000)throw Crypto.error("图片最多8,000万像素，单边不超过20,000。");return new int[]{w,h};}
    static Transport.Image load(Context c,Uri u)throws Exception{int[]wh=bounds(c,u);Runtime r=Runtime.getRuntime();long available=r.maxMemory()-(r.totalMemory()-r.freeMemory());if((long)wh[0]*wh[1]*8+32*1024*1024>available)throw Crypto.error("设备可用内存不足，请选择尺寸较小的图片。解密时请勿缩放原图。");BitmapFactory.Options options=new BitmapFactory.Options();options.inPreferredConfig=Bitmap.Config.ARGB_8888;options.inScaled=false;Bitmap b;try(InputStream in=stream(c,u)){b=BitmapFactory.decodeStream(in,null,options);}if(b==null)throw Crypto.error("图片无法读取，文件可能已损坏。");
        int orientation=1;try(InputStream in=stream(c,u)){orientation=new ExifInterface(in).getAttributeInt(ExifInterface.TAG_ORIENTATION,1);}catch(IOException ignored){}
        try{int w=b.getWidth(),h=b.getHeight();int[]p=new int[w*h];b.getPixels(p,0,w,0,0,w,h);for(int i=0;i<p.length;i++){int alpha=p[i]>>>24;if(alpha!=255){int red=((p[i]>>16&255)*alpha+255*(255-alpha)+127)/255,green=((p[i]>>8&255)*alpha+255*(255-alpha)+127)/255,blue=((p[i]&255)*alpha+255*(255-alpha)+127)/255;p[i]=0xff000000|(red<<16)|(green<<8)|blue;}}
            if(orientation>=2&&orientation<=8){int nw=orientation>=5?h:w,nh=orientation>=5?w:h;int[]out=new int[p.length];for(int y=0;y<h;y++)for(int x=0;x<w;x++){int nx=x,ny=y;switch(orientation){case 2:nx=w-1-x;break;case 3:nx=w-1-x;ny=h-1-y;break;case 4:ny=h-1-y;break;case 5:nx=y;ny=x;break;case 6:nx=h-1-y;ny=x;break;case 7:nx=h-1-y;ny=w-1-x;break;case 8:nx=y;ny=w-1-x;break;}out[ny*nw+nx]=p[y*w+x];}p=out;w=nw;h=nh;}return new Transport.Image(w,h,p);
        }finally{b.recycle();}}
    static Bitmap thumbnail(Transport.Image image){int w=Math.min(640,image.width),h=Math.max(1,(int)((long)image.height*w/image.width));if(h>360){w=Math.max(1,w*360/h);h=360;}int[]p=new int[w*h];for(int y=0;y<h;y++)for(int x=0;x<w;x++)p[y*w+x]=image.get(x*image.width/w,y*image.height/h);return Bitmap.createBitmap(p,w,h,Bitmap.Config.ARGB_8888);}
    // Stream PNG rows to avoid creating another full-size bitmap during saving.
    static void chunk(DataOutputStream out,String type,byte[]data)throws IOException{byte[]t=Crypto.bytes(type);CRC32 crc=new CRC32();crc.update(t);crc.update(data);out.writeInt(data.length);out.write(t);out.write(data);out.writeInt((int)crc.getValue());}
    static void png(Transport.Image image,File file)throws Exception{try(OutputStream out=new BufferedOutputStream(new FileOutputStream(file))){PngWriter.write(image,out,false);}}
}
