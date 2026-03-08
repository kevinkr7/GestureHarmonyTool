package com.harmony.gestureharmonytoolui;

import javafx.application.Platform;
import javafx.fxml.FXML;
import javafx.scene.control.*;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.VBox;
import javafx.scene.media.Media;
import javafx.scene.media.MediaPlayer;
import javafx.scene.media.MediaView;
import javafx.scene.web.WebView;
import javafx.stage.DirectoryChooser;
import javafx.stage.Window;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
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

    private MediaPlayer previewMediaPlayer;
    private Path harmonizedVideoPath;

    @FXML private Label sessionLabel;
    @FXML private Label status;
    @FXML private Label processingMessage;
    @FXML private Button startRecording;
    @FXML private Button stopRecording;
    @FXML private Button saveVideoButton;
    @FXML private VBox processingOverlay;
    @FXML private VBox previewPlaceholder;
    @FXML private HBox previewActions;

    @FXML private ComboBox<MediaDevice> videoDeviceComboBox;
    @FXML private ComboBox<MediaDevice> audioDeviceComboBox;

    @FXML private WebView feedbackWebView;
    @FXML private MediaView outputMediaView;

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
            return name;
        }
    }

    @FXML
    public void initialize() {
        loadHardwareDevices();
        hideProcessingOverlay();
        showPlaceholder("Live camera preview will appear here", "Click Create Session to start real-time gesture feedback.");
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

                    if (line.contains("\"")) {
                        String extractedName = extractBetweenQuotes(line);
                        if (extractedName == null) continue;

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

        }, "device-loader").start();
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
        SessionManager.writeConfig(currentSessionPath, config.key, config.scale, config.voices, config.mix);

        sessionLabel.setText("Session created: " + currentSessionPath);
        startRecording.setDisable(false);
        stopRecording.setDisable(true);
        saveVideoButton.setDisable(true);

        hideVideoPreview();
        boolean streamStarted = startLiveFeedbackStream();
        if (streamStarted) {
            status.setText("Session ready. Real-time gesture feedback is active.");
        }
    }

    @FXML
    protected void startRecordingOnClick() {
        if (currentSessionPath == null) {
            status.setText("Please create a session first.");
            return;
        }
        if (isRecording) return;

        if (!isLiveFeedbackRunning() && !startLiveFeedbackStream()) {
            status.setText("Unable to start live feedback stream.");
            return;
        }

        MediaDevice selectedVideo = videoDeviceComboBox.getValue();
        MediaDevice selectedAudio = audioDeviceComboBox.getValue();

        if (selectedVideo == null || selectedAudio == null) {
            status.setText("Error: Please select both a camera and a microphone.");
            return;
        }

        isRecording = true;

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

            status.setText("Recording started. Gesture feedback is visible live.");

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
        startRecording.setDisable(true);
        stopRecording.setDisable(true);

        if (ffmpegProcess == null) {
            status.setText("No active recording process.");
            startRecording.setDisable(false);
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
                stopLiveFeedbackStream();
                status.setText("Recording stopped. Rendering harmonized output...");
                runPostProcessingPipeline();
            } else {
                status.setText("Recording stop timed out; process may still be alive.");
                startRecording.setDisable(false);
            }

        } catch (Exception e) {
            status.setText("Error stopping recording.");
            e.printStackTrace();
            startRecording.setDisable(false);
        } finally {
            try { if (ffmpegStdin != null) ffmpegStdin.close(); } catch (IOException ignored) {}
            cleanupFfmpegHandles();
        }
    }

    @FXML
    protected void saveVideoOnClick() {
        if (harmonizedVideoPath == null || !Files.exists(harmonizedVideoPath)) {
            status.setText("No harmonized video available to save.");
            return;
        }

        DirectoryChooser chooser = new DirectoryChooser();
        chooser.setTitle("Choose directory to save harmonized video");

        Window window = status.getScene() != null ? status.getScene().getWindow() : null;
        File selectedDir = chooser.showDialog(window);
        if (selectedDir == null) {
            status.setText("Save cancelled.");
            return;
        }

        try {
            Path destination = selectedDir.toPath().resolve("harmonized_video.mp4");
            Files.copy(harmonizedVideoPath, destination, StandardCopyOption.REPLACE_EXISTING);
            status.setText("Saved: " + destination);
        } catch (IOException e) {
            status.setText("Failed to save harmonized video.");
            e.printStackTrace();
        }
    }

    private void cleanupFfmpegHandles() {
        ffmpegProcess = null;
        ffmpegStdin = null;
        ffmpegLogThread = null;
    }

    private boolean isLiveFeedbackRunning() {
        return cameraStreamProcess != null && cameraStreamProcess.isAlive();
    }

    private boolean startLiveFeedbackStream() {
        stopLiveFeedbackStream();

        List<String> command = new ArrayList<>();
        command.add("python");
        command.add(Path.of(AppPaths.ENGINE, "scripts", "live_gesture.py").toString());
        command.add("--serve");
        command.add("--host");
        command.add("127.0.0.1");
        command.add("--port");
        command.add(String.valueOf(CAMERA_STREAM_PORT));
        command.add("--camera-index");
        command.add("0");

        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(true);

        try {
            cameraStreamProcess = pb.start();
            cameraStreamLogThread = new Thread(() -> {
                try (BufferedReader br = new BufferedReader(
                        new InputStreamReader(cameraStreamProcess.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        System.out.println("[live_gesture] " + line);
                    }
                } catch (IOException ignored) {
                }
            }, "live-gesture-log");
            cameraStreamLogThread.setDaemon(true);
            cameraStreamLogThread.start();

            Thread.sleep(1000);
            if (!cameraStreamProcess.isAlive()) {
                status.setText("Live feedback stream exited unexpectedly.");
                return false;
            }

            String streamUrl = "http://127.0.0.1:" + CAMERA_STREAM_PORT + "/video?ts=" + System.currentTimeMillis();
            Platform.runLater(() -> {
                stopPreviewPlayer();
                outputMediaView.setVisible(false);
                outputMediaView.setManaged(false);
                feedbackWebView.setVisible(true);
                feedbackWebView.setManaged(true);
                previewPlaceholder.setVisible(false);
                previewPlaceholder.setManaged(false);
                feedbackWebView.getEngine().load(streamUrl);
            });

            return true;
        } catch (Exception e) {
            e.printStackTrace();
            status.setText("Failed to launch Python live feedback stream.");
            return false;
        }
    }

    private void stopLiveFeedbackStream() {
        Process process = cameraStreamProcess;
        cameraStreamProcess = null;

        if (process != null) {
            process.destroy();
            try {
                if (!process.waitFor(2, TimeUnit.SECONDS) && process.isAlive()) {
                    process.destroyForcibly();
                    process.waitFor(2, TimeUnit.SECONDS);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        cameraStreamLogThread = null;
        Platform.runLater(() -> feedbackWebView.getEngine().load("about:blank"));
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

                updateProcessingMessage("Building harmonized video preview...");
                Path outputVideo = muxFinalVideo(Path.of(currentSessionPath));
                harmonizedVideoPath = outputVideo;

                Platform.runLater(() -> {
                    hideProcessingOverlay();
                    showVideoPreview(outputVideo);
                    saveVideoButton.setDisable(false);
                    startRecording.setDisable(false);
                    stopRecording.setDisable(true);
                    status.setText("Processing complete! Preview the harmonized result, then save if satisfied.");
                });
            } catch (Exception e) {
                Platform.runLater(() -> {
                    hideProcessingOverlay();
                    startRecording.setDisable(false);
                    stopRecording.setDisable(true);
                    status.setText("Background processing failed. Check logs for details.");
                });
                e.printStackTrace();
            }
        }, "post-process-pipeline");

        pipelineThread.setDaemon(true);
        pipelineThread.start();
    }

    private Path muxFinalVideo(Path sessionDir) throws IOException, InterruptedException {
        Path inputVideo = sessionDir.resolve("video.mp4");
        Path harmonizedAudio = sessionDir.resolve("harmonized_enhanced.wav");
        Path finalVideo = sessionDir.resolve("harmonized_video.mp4");

        ProcessBuilder pb = new ProcessBuilder(
                "ffmpeg", "-y",
                "-i", inputVideo.toString(),
                "-i", harmonizedAudio.toString(),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                finalVideo.toString()
        );
        pb.redirectErrorStream(true);
        Process process = pb.start();

        try (BufferedReader br = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = br.readLine()) != null) {
                System.out.println("[ffmpeg-mux] " + line);
            }
        }

        int exit = process.waitFor();
        if (exit != 0 || !Files.exists(finalVideo)) {
            throw new IOException("Failed to build harmonized video preview.");
        }
        return finalVideo;
    }

    private void showVideoPreview(Path videoPath) {
        stopPreviewPlayer();

        feedbackWebView.setVisible(false);
        feedbackWebView.setManaged(false);
        previewPlaceholder.setVisible(false);
        previewPlaceholder.setManaged(false);
        outputMediaView.setVisible(true);
        outputMediaView.setManaged(true);

        Media media = new Media(videoPath.toUri().toString());
        previewMediaPlayer = new MediaPlayer(media);
        previewMediaPlayer.setAutoPlay(true);
        outputMediaView.setMediaPlayer(previewMediaPlayer);

        previewActions.setVisible(true);
        previewActions.setManaged(true);
    }

    private void hideVideoPreview() {
        stopPreviewPlayer();
        outputMediaView.setVisible(false);
        outputMediaView.setManaged(false);
        previewActions.setVisible(false);
        previewActions.setManaged(false);
    }

    private void showPlaceholder(String title, String subtitle) {
        hideVideoPreview();
        feedbackWebView.setVisible(false);
        feedbackWebView.setManaged(false);

        if (!previewPlaceholder.getChildren().isEmpty() && previewPlaceholder.getChildren().size() >= 2) {
            if (previewPlaceholder.getChildren().get(0) instanceof Label titleLabel) {
                titleLabel.setText(title);
            }
            if (previewPlaceholder.getChildren().get(1) instanceof Label subtitleLabel) {
                subtitleLabel.setText(subtitle);
            }
        }

        previewPlaceholder.setVisible(true);
        previewPlaceholder.setManaged(true);
    }

    private void stopPreviewPlayer() {
        if (previewMediaPlayer != null) {
            previewMediaPlayer.stop();
            previewMediaPlayer.dispose();
            previewMediaPlayer = null;
        }
        outputMediaView.setMediaPlayer(null);
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

    public void shutdown() {
        isRecording = false;
        if (ffmpegProcess != null && ffmpegProcess.isAlive()) {
            ffmpegProcess.destroyForcibly();
        }
        stopLiveFeedbackStream();
        stopPreviewPlayer();
    }
}
