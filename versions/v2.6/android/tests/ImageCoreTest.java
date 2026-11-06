package org.binarypasscode.image;

import java.io.*;
import java.nio.file.*;
import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.util.*;

/** Host-only interop harness; never included in the APK. */
public final class ImageCoreTest {
    static String key="01234567";static{while(key.length()<128)key+=key;}
    public static void main(String[]args)throws Exception{
        if(args[0].equals("decode")){Transport.Image image=CoreTest.load(args[1]);Transport.Result r=Transport.decode(image,args.length>3?args[3]:key,null);if(r.image==null){Files.write(Paths.get(args[2]),Crypto.bytes(r.message.text));System.out.println("TEXT "+r.message.seconds);}else{Files.write(Paths.get(args[2]),r.image.data);System.out.println((r.image.png?"PNG ":"JPEG ")+r.image.width+"x"+r.image.height+" time="+r.message.seconds);}return;}
        if(args[0].equals("rawpng")){int w=37,h=29;int[]pixels=new int[w*h];Random random=new Random(73);for(int i=0;i<pixels.length;i++)pixels[i]=random.nextInt();byte[]data=PngWriter.encode(new Transport.Image(w,h,pixels),true);Files.write(Paths.get(args[1]),data);BufferedImage decoded=ImageIO.read(new ByteArrayInputStream(data));for(int y=0;y<h;y++)for(int x=0;x<w;x++)if(decoded.getRGB(x,y)!=pixels[y*w+x])throw new AssertionError("RGBA changed");System.out.println("RAW RGBA PASS");return;}
        Transport.Image carrier=CoreTest.load(args[1]);byte[]data=Files.readAllBytes(Paths.get(args[2]));BufferedImage secret=ImageIO.read(new ByteArrayInputStream(data));boolean png=args[0].equals("png");ImagePayload.Prepared p=new ImagePayload.Prepared(data,secret.getWidth(),secret.getHeight(),png?0:75,png,secret.getWidth(),secret.getHeight());byte[]nonce=new byte[48];for(int i=0;i<48;i++)nonce[i]=(byte)i;byte[]envelope=ImagePayload.seal(p,key,1793701842L,nonce);if(!Arrays.equals(ImagePayload.open(envelope,key).image.data,data))throw new AssertionError();Files.write(Paths.get(args[3]+".envelope"),envelope);System.out.println("envelope ready");if(png)DenseTransport.encode(carrier,envelope,key,null);else Transport.encodeEnvelope(carrier,envelope,key,args.length>4&&args[4].equals("strong"),null);System.out.println("pixels ready; writing PNG");try(OutputStream out=new BufferedOutputStream(new FileOutputStream(args[3]))){PngWriter.write(carrier,out,false);}System.out.println("ENCODE "+data.length+" bytes");
    }
}
