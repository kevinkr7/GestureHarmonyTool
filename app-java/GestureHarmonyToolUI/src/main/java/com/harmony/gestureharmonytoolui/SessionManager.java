package com.harmony.gestureharmonytoolui;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public class SessionManager {
    public static String createNewSession(){
        String base = AppPaths.SESSIONS;
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss");
        String id = LocalDateTime.now().format(formatter);
        String folderName = base+"/session_"+id;

        File file = new File(folderName);
        file.mkdir();
        return file.getAbsolutePath();

    }

    public static void writeConfig(String sessionPath, String key, String scale, int voices, double mix){
        String filepath = sessionPath+"/config.json";

        String jsonText="{\n" +
                "  \"key\": \"" + key + "\",\n" +
                "  \"scale\": \"" + scale + "\",\n" +
                "  \"voices\": \"" + voices + "\",\n" +
                "  \"mix\": \"" + mix + "\"\n" +
                "}";


            try(FileWriter writer = new FileWriter(filepath)){
                writer.write(jsonText);
                writer.flush();
            } catch(IOException e){
                e.printStackTrace();
            }

    }
}
