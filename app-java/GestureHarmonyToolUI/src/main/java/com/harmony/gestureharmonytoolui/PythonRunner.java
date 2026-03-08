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
                System.out.println("[gesture] " + line);
            }
            int exitCode = process.waitFor();
            System.out.println("Gesture analysis exited with code: "+exitCode);
        } catch(Exception e){
            e.printStackTrace();
        }
    }

    public void runHarmonizeAudio(String sessionPath){
        ProcessBuilder pb = new ProcessBuilder("python", "C:\\College\\Projects\\GestureHarmonyTool\\engine-py\\scripts\\harmonize_audio.py", sessionPath);
        pb.redirectErrorStream(true);
        try{
            Process process = pb.start();

            BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
            String line;
            while((line=reader.readLine())!=null){
                System.out.println("[harmonize] "+line);
            }

            int exitCode = process.waitFor();
            System.out.println("Harmonize exited with code: "+exitCode);

        }catch(Exception e){
            e.printStackTrace();
        }
    }
}
