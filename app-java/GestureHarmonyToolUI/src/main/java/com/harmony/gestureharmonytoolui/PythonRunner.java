package com.harmony.gestureharmonytoolui;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class PythonRunner {

    public void runAnalyzeSession(String sessionPath) throws IOException, InterruptedException {
        runScript("gesture", Path.of(AppPaths.ENGINE, "scripts", "live_gesture.py").toString(), sessionPath);
    }

    public void runHarmonizeAudio(String sessionPath) throws IOException, InterruptedException {
        runScript("harmonize", Path.of(AppPaths.ENGINE, "scripts", "harmonize_audio.py").toString(), sessionPath);
    }

    private void runScript(String tag, String scriptPath, String sessionPath) throws IOException, InterruptedException {
        ProcessBuilder pb = new ProcessBuilder("python", scriptPath, sessionPath);
        pb.redirectErrorStream(true);
        pb.directory(new File("."));

        Process process = pb.start();
        List<String> recentLogs = new ArrayList<>();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("[" + tag + "] " + line);
                recentLogs.add(line);
                if (recentLogs.size() > 40) {
                    recentLogs.remove(0);
                }
            }
        }

        int exitCode = process.waitFor();
        if (exitCode != 0) {
            throw new IOException("Python step failed (" + tag + ") exit=" + exitCode + " logs=" + String.join(" | ", recentLogs));
        }
    }
}
