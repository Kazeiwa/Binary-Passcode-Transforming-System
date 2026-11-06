package org.binarypasscode.image;

import android.content.*;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.*;
import android.provider.MediaStore;
import java.io.*;
import java.util.UUID;

/** Writes original image bytes; previews and bitmap compression never enter this path. */
final class GalleryImages {
    static Uri save(Context context,InputStream input,boolean png,String prefix)throws Exception {
        String name=prefix+"_"+System.currentTimeMillis()+"_"+UUID.randomUUID().toString().substring(0,8)+(png?".png":".jpg");
        String mime=png?"image/png":"image/jpeg";
        ContentResolver resolver=context.getContentResolver();
        if(Build.VERSION.SDK_INT>=29){
            ContentValues values=new ContentValues();values.put(MediaStore.Images.Media.DISPLAY_NAME,name);values.put(MediaStore.Images.Media.MIME_TYPE,mime);
            values.put(MediaStore.Images.Media.RELATIVE_PATH,Environment.DIRECTORY_PICTURES+"/BinaryImagePasscode");values.put(MediaStore.Images.Media.IS_PENDING,1);
            Uri uri=resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,values);
            if(uri==null)throw new IOException("无法在相册创建图片，请尝试保存到文件。");
            try{
                try(OutputStream out=resolver.openOutputStream(uri,"w")){if(out==null)throw new IOException("无法写入相册。");copy(input,out);}
                Crypto.check();ContentValues ready=new ContentValues();ready.put(MediaStore.Images.Media.IS_PENDING,0);
                if(resolver.update(uri,ready,null,null)!=1)throw new IOException("相册未能确认图片保存，请重试。");
                return uri;
            }catch(Exception e){try{resolver.delete(uri,null,null);}catch(Exception ignored){}throw e;}
        }
        File folder=new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES),"BinaryImagePasscode");
        if(!folder.isDirectory()&&!folder.mkdirs())throw new IOException("无法创建相册目录，请尝试保存到文件。");
        File file=new File(folder,name);
        try{try(OutputStream out=new FileOutputStream(file)){copy(input,out);}Crypto.check();MediaScannerConnection.scanFile(context,new String[]{file.getAbsolutePath()},new String[]{mime},null);return Uri.fromFile(file);}
        catch(Exception e){file.delete();throw e;}
    }
    private static void copy(InputStream in,OutputStream out)throws Exception{byte[]buffer=new byte[65536];int n;while((n=in.read(buffer))!=-1){Crypto.check();out.write(buffer,0,n);}out.flush();}
}
