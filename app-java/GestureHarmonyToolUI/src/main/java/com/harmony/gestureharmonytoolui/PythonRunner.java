package com.harmony.gestureharmonytoolui;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;

public class PythonRunner {
    public void runAnalyzeSession(String sessionPath){
        String scriptPath = "C:\\College\\Projects\\GestureHarmonyTool\\engine-py\\scripts\\live_gesture.py";
        ProcessBuilder pb = new ProcessBuilder("python", scriptPath, sessionPath);
        pb.redirectErrorStream(true);
        pb.directory(new File("."));

        try {
            Process process = pb.start();
            BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));

            String line;
            while((line = reader.readLine()) != null) {
                System.out.println(line);
            }
            int exitCode = process.waitFor();
            System.out.println("Python exited with code: "+exitCode);
        } catch(Exception e){
            e.printStackTrace();
        }
    }

    public void runHarmonizeAudio(String sessionPath){
        String audioPath = sessionPath+"/audio.wav";
        ProcessBuilder pb = new ProcessBuilder("python", "C:\\College\\Projects\\GestureHarmonyTool\\engine-py\\scripts\\harmonize_audio.py", sessionPath);
        pb.redirectErrorStream(true);
        try{
            Process process = pb.start();
            process.waitFor();

            BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
            String line;
            while((line=reader.readLine())!=null){
                System.out.println("[harmonize] "+line);
            }

            int exitCode = process.waitFor();
            System.out.println("Harmonize with code: "+exitCode);

        }catch(Exception e){
            e.printStackTrace();
        }
    }
}
