package com.harmony.gestureharmonytoolui;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class FfmpegUtils {

    public String extractWav(String sessionPath){
        String input = sessionPath+"/video.mp4";
        String output = sessionPath + "/output.wav";

        ProcessBuilder pb = new ProcessBuilder("ffmpeg", "-y", "-i", input, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1", output);
        pb.redirectErrorStream(true);
        try {
            Process process = pb.start();

            BufferedReader reader =
                    new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8));

            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("[ffmpeg] " + line);
            }

            int exit = process.waitFor();

            if (exit == 0 && new File(output).exists()) {
                return output;
            }
        }catch(Exception e){
            e.printStackTrace();
        }
        return null;
    }
}
