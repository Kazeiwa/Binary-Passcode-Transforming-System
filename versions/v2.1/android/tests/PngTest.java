package org.binarypasscode.image;
import java.io.File;
/** Uses the exact streaming PNG writer shipped in the APK. */
public class PngTest {
    public static void main(String[]args)throws Exception{
        Transport.Image image=CoreTest.load(args[0]);Images.png(image,new File(args[1]));
        Transport.Image reread=CoreTest.load(args[1]);
        if(image.width!=reread.width||image.height!=reread.height)throw new AssertionError();
        for(int i=0;i<image.pixels.length;i++)if((image.pixels[i]&0xffffff)!=(reread.pixels[i]&0xffffff))throw new AssertionError();
        System.out.println("PASS APK PNG writer: every RGB byte preserved");
    }
}
