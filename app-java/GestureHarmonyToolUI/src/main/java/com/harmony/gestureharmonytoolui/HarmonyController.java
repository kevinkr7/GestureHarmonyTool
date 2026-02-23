package com.harmony.gestureharmonytoolui;

import javafx.application.Platform;
import javafx.fxml.FXML;
import javafx.scene.control.*;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.VBox;
import javafx.scene.web.WebView;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;


public class HarmonyController {

    private String currentSessionPath;
    private boolean isRecording;
    private Process ffmpegProcess;
    private BufferedWriter ffmpegStdin;
    private Thread ffmpegLogThread;
    private Process cameraStreamProcess;
    private Thread cameraStreamLogThread;

    private static final int CAMERA_STREAM_PORT = 5051;

    @FXML private Label sessionLabel;
    @FXML private Label status;
    @FXML private Label processingMessage;
    @FXML private Button startRecording;
    @FXML private Button stopRecording;
    @FXML private VBox processingOverlay;
    @FXML private VBox previewPlaceholder;

    // New Dropdowns for Hardware Selection
    @FXML private ComboBox<MediaDevice> videoDeviceComboBox;
    @FXML private ComboBox<MediaDevice> audioDeviceComboBox;

    /**
     * Nested class to store the friendly name and the FFmpeg alternative hardware path.
     */
    public static class MediaDevice {
        private final String name;
        private String altName;

        public MediaDevice(String name) {
            this.name = name;
        }

        public void setAltName(String altName) {
            this.altName = altName;
        }

        public String getAltName() {
            return altName;
        }

        @Override
        public String toString() {
            return name; // This controls what the user actually sees in the ComboBox
        }
    }

    @FXML
    public void initialize() {
        // Automatically fetch and populate devices when the UI loads
        loadHardwareDevices();
        hideProcessingOverlay();

        videoDeviceComboBox.valueProperty().addListener((obs, oldDevice, newDevice) -> {
            if (newDevice != null && currentSessionPath != null && !isRecording) {
                startCamera();
            }
        });
    }

    private void loadHardwareDevices() {
        status.setText("Loading hardware devices...");

        new Thread(() -> {
            List<MediaDevice> videoDevices = new ArrayList<>();
            List<MediaDevice> audioDevices = new ArrayList<>();

            try {
                ProcessBuilder pb = new ProcessBuilder(
                        "ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"
                );
                pb.redirectErrorStream(true);
                Process process = pb.start();

                BufferedReader reader = new BufferedReader(
                        new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8)
                );

                String line;
                MediaDevice currentDevice = null;

                while ((line = reader.readLine()) != null) {

                    System.out.println("[Device Scan] " + line);
                    String lowerLine = line.toLowerCase();

                    // Only process lines containing quoted device names
                    if (line.contains("\"")) {

                        String extractedName = extractBetweenQuotes(line);
                        if (extractedName == null) continue;

                        // Detect device type from line (FFmpeg 8.x format)
                        if (lowerLine.contains("(video)")) {

                            currentDevice = new MediaDevice(extractedName);
                            videoDevices.add(currentDevice);

                        } else if (lowerLine.contains("(audio)")) {

                            currentDevice = new MediaDevice(extractedName);
                            audioDevices.add(currentDevice);

                        } else if (lowerLine.contains("alternative name") && currentDevice != null) {

                            currentDevice.setAltName(extractedName);
                        }
                    }
                }

                process.waitFor(2, TimeUnit.SECONDS);

            } catch (Exception e) {
                e.printStackTrace();
                Platform.runLater(() -> status.setText("Failed to load hardware devices."));
                return;
            }

            // Update UI safely on JavaFX Application Thread
            Platform.runLater(() -> {
                videoDeviceComboBox.getItems().setAll(videoDevices);
                audioDeviceComboBox.getItems().setAll(audioDevices);

                if (!videoDevices.isEmpty()) {
                    videoDeviceComboBox.getSelectionModel().selectFirst();
                }

                if (!audioDevices.isEmpty()) {
                    audioDeviceComboBox.getSelectionModel().selectFirst();
                }

                status.setText("Devices loaded successfully.");
            });

        }).start();
    }
    private String extractBetweenQuotes(String text) {
        int start = text.indexOf('"');
        int end = text.lastIndexOf('"');
        if (start != -1 && end != -1 && start < end) {
            return text.substring(start + 1, end);
        }
        return null;
    }

    private SessionConfig promptForSessionConfig() {

        Dialog<SessionConfig> dialog = new Dialog<>();
        dialog.setTitle("Session Configuration");
        dialog.setHeaderText("Configure Harmony Settings");

        ButtonType createButtonType = new ButtonType("Create", ButtonBar.ButtonData.OK_DONE);
        dialog.getDialogPane().getButtonTypes().addAll(createButtonType, ButtonType.CANCEL);

        // Inputs
        ComboBox<String> keyBox = new ComboBox<>();
        keyBox.getItems().addAll("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B");
        keyBox.getSelectionModel().select("C");

        ComboBox<String> scaleBox = new ComboBox<>();
        scaleBox.getItems().addAll("major", "minor");
        scaleBox.getSelectionModel().select("major");

        Spinner<Integer> voicesSpinner = new Spinner<>(1, 8, 1);

        Spinner<Double> mixSpinner = new Spinner<>(0.0, 1.0, 0.5, 0.1);
        mixSpinner.setEditable(true);

        GridPane grid = new GridPane();
        grid.setHgap(10);
        grid.setVgap(10);

        grid.add(new Label("Key:"), 0, 0);
        grid.add(keyBox, 1, 0);
        grid.add(new Label("Scale:"), 0, 1);
        grid.add(scaleBox, 1, 1);
        grid.add(new Label("Voices:"), 0, 2);
        grid.add(voicesSpinner, 1, 2);
        grid.add(new Label("Mix:"), 0, 3);
        grid.add(mixSpinner, 1, 3);

        dialog.getDialogPane().setContent(grid);

        dialog.setResultConverter(dialogButton -> {
            if (dialogButton == createButtonType) {
                return new SessionConfig(
                        keyBox.getValue(),
                        scaleBox.getValue(),
                        voicesSpinner.getValue(),
                        mixSpinner.getValue()
                );
            }
            return null;
        });

        return dialog.showAndWait().orElse(null);
    }

    @FXML
    protected void createSessionOnClick() {

        SessionConfig config = promptForSessionConfig();

        if (config == null) {
            status.setText("Session creation cancelled.");
            return;
        }

        currentSessionPath = SessionManager.createNewSession();

        SessionManager.writeConfig(
                currentSessionPath,
                config.key,
                config.scale,
                config.voices,
                config.mix
        );

        sessionLabel.setText("Session created: " + currentSessionPath);
        status.setText("Session ready. Live camera preview is active.");

        startCamera();

        startRecording.setDisable(false);
        stopRecording.setDisable(true);

    }

    @FXML
    protected void startRecordingOnClick() {
        if (currentSessionPath == null) {
            status.setText("Please create a session first.");
            return;
        }
        if (isRecording) return;

        MediaDevice selectedVideo = videoDeviceComboBox.getValue();
        MediaDevice selectedAudio = audioDeviceComboBox.getValue();

        if (selectedVideo == null || selectedAudio == null) {
            status.setText("Error: Please select both a camera and a microphone.");
            return;
        }

        isRecording = true;

        // Free the capture device before starting the recorder process.
        stopCamera();

        Path sessionDir = Path.of(currentSessionPath);
        try {
            Files.createDirectories(sessionDir);
        } catch (IOException e) {
            status.setText("Failed to create session dir");
            e.printStackTrace();
            isRecording = false;
            return;
        }

        String videoPath = sessionDir.resolve("video.mp4").toString();

        // Feed the dynamically selected alternative names to FFmpeg
        String videoAlt = selectedVideo.getAltName();
        String audioAlt = selectedAudio.getAltName();
        String device = "video=\"" + videoAlt + "\":audio=\"" + audioAlt + "\"";

        ProcessBuilder pb = new ProcessBuilder(
                "ffmpeg",
                "-y",
                "-f", "dshow",
                "-i", device,
                "-r", "30",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                videoPath
        );

        pb.redirectErrorStream(true);

        try {
            ffmpegProcess = pb.start();

            ffmpegStdin = new BufferedWriter(
                    new OutputStreamWriter(ffmpegProcess.getOutputStream(), StandardCharsets.UTF_8)
            );

            ffmpegLogThread = new Thread(() -> {
                try (BufferedReader br = new BufferedReader(
                        new InputStreamReader(ffmpegProcess.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        System.out.println("[ffmpeg] " + line);
                    }
                } catch (IOException ignored) {}
            }, "ffmpeg-log-drain");
            ffmpegLogThread.setDaemon(true);
            ffmpegLogThread.start();

            status.setText("Recording started...");

        } catch (Exception e) {
            status.setText("Failed to start recording (ffmpeg).");
            e.printStackTrace();
            cleanupFfmpegHandles();
            isRecording = false;
            startRecording.setDisable(false);
            stopRecording.setDisable(true);
            return;
        }

        startRecording.setDisable(true);
        stopRecording.setDisable(false);
    }

    @FXML
    protected void stopRecordingOnClick() {
        if (!isRecording) return;
        isRecording = false;

        status.setText("Stopping recording...");
        startRecording.setDisable(false);
        stopRecording.setDisable(true);

        if (ffmpegProcess == null) {
            status.setText("No active recording process.");
            return;
        }

        try {
            if (ffmpegProcess.isAlive() && ffmpegStdin != null) {
                ffmpegStdin.write("q\n");
                ffmpegStdin.flush();
            }

            boolean exited = ffmpegProcess.waitFor(5, TimeUnit.SECONDS);

            if (!exited && ffmpegProcess.isAlive()) {
                ffmpegProcess.destroyForcibly();
                ffmpegProcess.waitFor(3, TimeUnit.SECONDS);
            }

            if (!ffmpegProcess.isAlive()) {
                status.setText("Recording stopped. Rendering final harmony in the background...");
                runPostProcessingPipeline();
            } else {
                status.setText("Recording stop timed out; process may still be alive.");
            }

        } catch (Exception e) {
            status.setText("Error stopping recording.");
            e.printStackTrace();
        } finally {
            try { if (ffmpegStdin != null) ffmpegStdin.close(); } catch (IOException ignored) {}
            cleanupFfmpegHandles();
        }

        startRecording.setDisable(false);
        stopRecording.setDisable(true);

        // Restart live preview after recording has released the camera.
        startCamera();
    }

    private void cleanupFfmpegHandles() {
        ffmpegProcess = null;
        ffmpegStdin = null;
        ffmpegLogThread = null;
    }

    @FXML
    private WebView cameraView;


    public void startCamera() {
        MediaDevice selectedVideo = videoDeviceComboBox.getValue();
        if (selectedVideo == null) {
            status.setText("Camera preview unavailable: no video device selected.");
            return;
        }

        String videoSource = selectedVideo.getAltName() != null ? selectedVideo.getAltName() : selectedVideo.toString();

        stopCamera();

        ProcessBuilder pb = new ProcessBuilder(
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "warning",
                "-f", "dshow",
                "-i", "video=\"" + videoSource + "\"",
                "-an",
                "-vf", "scale=960:540",
                "-q:v", "5",
                "-f", "mjpeg",
                "-listen", "1",
                "http://127.0.0.1:" + CAMERA_STREAM_PORT + "/feed"
        );
        pb.redirectErrorStream(true);

        try {
            cameraStreamProcess = pb.start();

            cameraStreamLogThread = new Thread(() -> {
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(cameraStreamProcess.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        System.out.println("[camera-preview] " + line);
                    }
                } catch (IOException ignored) {
                }
            }, "camera-preview-log-drain");
            cameraStreamLogThread.setDaemon(true);
            cameraStreamLogThread.start();


            String previewHtml = """
                    <!DOCTYPE html>
                    <html lang=\"en\">
                    <head>
                      <meta charset=\"UTF-8\" />
                      <style>
                        html, body { margin: 0; background: #020617; width: 100%; height: 100%; }
                        .wrap { position: relative; width: 100%; height: 100%; }
                        img { width: 100%; height: 100%; object-fit: cover; border-radius: 14px; transform: scaleX(-1); }
                        .badge {
                          position: absolute; top: 16px; left: 16px; padding: 8px 12px;
                          background: rgba(15, 23, 42, 0.7); color: #e2e8f0; border-radius: 999px;
                          font: 600 13px Arial, sans-serif;
                        }
                      </style>
                    </head>
                    <body>
                      <div class=\"wrap\">
                        <span class=\"badge\">● Live Camera</span>
                        <img src=\"http://127.0.0.1:""" + CAMERA_STREAM_PORT + """/feed\" alt=\"Camera feed\" />
                      </div>
                    </body>
                    </html>
                    """;

            cameraView.getEngine().loadContent(previewHtml);
            cameraView.setVisible(true);
            cameraView.setManaged(true);
            previewPlaceholder.setVisible(false);
            previewPlaceholder.setManaged(false);
            status.setText("Session ready. Live camera preview is active.");
        } catch (Exception e) {
            stopCamera();
            previewPlaceholder.setVisible(true);
            previewPlaceholder.setManaged(true);
            cameraView.setVisible(false);
            cameraView.setManaged(false);
            status.setText("Unable to open camera preview. Check FFmpeg and camera permissions.");
            e.printStackTrace();
            status.setText("Unable to open camera preview.");
        }
    }

    public void stopCamera() {
        if (cameraStreamProcess != null && cameraStreamProcess.isAlive()) {
            cameraStreamProcess.destroy();
            try {
                cameraStreamProcess.waitFor(2, TimeUnit.SECONDS);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
            if (cameraStreamProcess.isAlive()) {
                cameraStreamProcess.destroyForcibly();
            }
        }

        cameraStreamProcess = null;
        cameraStreamLogThread = null;
    }

    private void runPostProcessingPipeline() {
        showProcessingOverlay();

        Thread pipelineThread = new Thread(() -> {
            try {
                updateProcessingMessage("Analyzing gesture flow...");
                new PythonRunner().runAnalyzeSession(currentSessionPath);

                updateProcessingMessage("Extracting clean audio for harmony blending...");
                new FfmpegUtils().extractWav(currentSessionPath);

                updateProcessingMessage("Composing harmonized output...");
                new PythonRunner().runHarmonizeAudio(currentSessionPath);

                Platform.runLater(() -> {
                    hideProcessingOverlay();
                    status.setText("Processing complete! Your harmonized output is ready.");
                });
            } catch (Exception e) {
                Platform.runLater(() -> {
                    hideProcessingOverlay();
                    status.setText("Background processing failed. Check logs for details.");
                });
                e.printStackTrace();
            }
        }, "post-process-pipeline");

        pipelineThread.setDaemon(true);
        pipelineThread.start();
    }

    private void showProcessingOverlay() {
        Platform.runLater(() -> {
            processingOverlay.setVisible(true);
            processingOverlay.setManaged(true);
            updateProcessingMessage("Preparing processing pipeline...");
        });
    }

    private void hideProcessingOverlay() {
        processingOverlay.setVisible(false);
        processingOverlay.setManaged(false);
        updateProcessingMessage("");
    }

    private void updateProcessingMessage(String message) {
        Platform.runLater(() -> processingMessage.setText(message));
    }
}
