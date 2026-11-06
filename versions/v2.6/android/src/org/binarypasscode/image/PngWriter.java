package org.binarypasscode.image;

import java.io.*;
import java.util.zip.*;

/** Streaming 8-bit RGB/RGBA PNG; unassociated alpha values are preserved exactly. */
public final class PngWriter {
    static void chunk(DataOutputStream out,String name,byte[]data)throws IOException{byte[]type=Crypto.bytes(name);CRC32 crc=new CRC32();crc.update(type);crc.update(data);out.writeInt(data.length);out.write(type);out.write(data);out.writeInt((int)crc.getValue());}
    public static byte[] encode(Transport.Image image,boolean alpha)throws IOException{ByteArrayOutputStream out=new ByteArrayOutputStream();write(image,out,alpha);return out.toByteArray();}
    public static void write(Transport.Image image,OutputStream stream,boolean alpha)throws IOException{DataOutputStream out=new DataOutputStream(stream);out.write(new byte[]{(byte)137,80,78,71,13,10,26,10});chunk(out,"IHDR",Crypto.cat(Crypto.number(image.width,4),Crypto.number(image.height,4),new byte[]{8,(byte)(alpha?6:2),0,0,0}));OutputStream chunks=new OutputStream(){ByteArrayOutputStream buffer=new ByteArrayOutputStream();public void write(int b)throws IOException{buffer.write(b);if(buffer.size()==65536)flush();}public void write(byte[]b,int off,int len)throws IOException{while(len>0){int n=Math.min(len,65536-buffer.size());buffer.write(b,off,n);off+=n;len-=n;if(buffer.size()==65536)flush();}}public void flush()throws IOException{if(buffer.size()>0){chunk(out,"IDAT",buffer.toByteArray());buffer.reset();}}};Deflater deflater=new Deflater(6);try{DeflaterOutputStream zip=new DeflaterOutputStream(chunks,deflater,32768);int channels=alpha?4:3;byte[]row=new byte[image.width*channels+1];for(int y=0;y<image.height;y++){Crypto.check();for(int x=0;x<image.width;x++){int p=image.get(x,y),o=1+x*channels;row[o]=(byte)(p>>16);row[o+1]=(byte)(p>>8);row[o+2]=(byte)p;if(alpha)row[o+3]=(byte)(p>>>24);}row[0]=1;for(int i=row.length-1;i>channels;i--)row[i]=(byte)(row[i]-row[i-channels]);zip.write(row);}zip.finish();chunks.flush();chunk(out,"IEND",new byte[0]);out.flush();}finally{deflater.end();}}
}
