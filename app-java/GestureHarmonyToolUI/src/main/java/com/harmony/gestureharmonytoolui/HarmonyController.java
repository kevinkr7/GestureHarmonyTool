package com.harmony.gestureharmonytoolui;

import javafx.application.Platform;
import javafx.fxml.FXML;
import javafx.scene.control.*;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.VBox;
import javafx.scene.image.Image;
import javafx.scene.image.ImageView;
import javafx.scene.media.Media;
import javafx.scene.media.MediaPlayer;
import javafx.scene.media.MediaView;
import javafx.stage.DirectoryChooser;
import javafx.stage.Window;

import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public class HarmonyController {

    private String currentSessionPath;
    private boolean isRecording;
    private Process ffmpegProcess;
    private BufferedWriter ffmpegStdin;
    private Thread ffmpegLogThread;
    private final List<String> recentFfmpegLogs = Collections.synchronizedList(new ArrayList<>());

    private Process cameraStreamProcess;
    private Thread cameraStreamLogThread;
    private static final int CAMERA_STREAM_PORT = 5051;

    private MediaPlayer previewMediaPlayer;
    private ScheduledExecutorService feedbackFramePoller;
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

    @FXML private ImageView feedbackImageView;
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
            Set<String> seenVideoNames = new LinkedHashSet<>();
            Set<String> seenAudioNames = new LinkedHashSet<>();

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
                final int SECTION_NONE = 0;
                final int SECTION_VIDEO = 1;
                final int SECTION_AUDIO = 2;
                int currentSection = SECTION_NONE;

                while ((line = reader.readLine()) != null) {
                    System.out.println("[Device Scan] " + line);
                    String lowerLine = line.toLowerCase();

                    if (lowerLine.contains("directshow video devices") || lowerLine.contains("video devices")) {
                        currentSection = SECTION_VIDEO;
                        currentDevice = null;
                        continue;
                    }
                    if (lowerLine.contains("directshow audio devices") || lowerLine.contains("audio devices")) {
                        currentSection = SECTION_AUDIO;
                        currentDevice = null;
                        continue;
                    }

                    if (!line.contains("\"")) {
                        continue;
                    }

                    String extractedName = extractBetweenQuotes(line);
                    if (extractedName == null) {
                        continue;
                    }

                    if (lowerLine.contains("alternative name") && currentDevice != null) {
                        currentDevice.setAltName(extractedName);
                        continue;
                    }

                    if (lowerLine.contains("(video)")) {
                        if (seenVideoNames.add(extractedName)) {
                            currentDevice = new MediaDevice(extractedName);
                            videoDevices.add(currentDevice);
                        }
                        continue;
                    }
                    if (lowerLine.contains("(audio)")) {
                        if (seenAudioNames.add(extractedName)) {
                            currentDevice = new MediaDevice(extractedName);
                            audioDevices.add(currentDevice);
                        }
                        continue;
                    }

                    if (currentSection == SECTION_VIDEO) {
                        if (seenVideoNames.add(extractedName)) {
                            currentDevice = new MediaDevice(extractedName);
                            videoDevices.add(currentDevice);
                        }
                    } else if (currentSection == SECTION_AUDIO) {
                        if (seenAudioNames.add(extractedName)) {
                            currentDevice = new MediaDevice(extractedName);
                            audioDevices.add(currentDevice);
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

                status.setText("Devices loaded successfully. Video: " + videoDevices.size() + ", Audio: " + audioDevices.size());
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

        String primaryVideoName = selectedVideo.toString();
        String primaryAudioName = selectedAudio.toString();

        notifyPythonRecordingStart();
        boolean started = startFfmpegRecording(buildRecordingCommand(primaryVideoName, primaryAudioName, videoPath));

        if (!started) {
            String altVideo = selectedVideo.getAltName();
            String altAudio = selectedAudio.getAltName();
            boolean hasAltPair = altVideo != null && altAudio != null
                    && (!altVideo.equals(primaryVideoName) || !altAudio.equals(primaryAudioName));

            if (hasAltPair) {
                status.setText("Retrying recording with alternative device identifiers...");
                started = startFfmpegRecording(buildRecordingCommand(altVideo, altAudio, videoPath));
            }
        }

        if (!started) {
            notifyPythonRecordingStop();
            status.setText("Failed to start recording. Check selected camera/microphone or ffmpeg logs.");
            isRecording = false;
            startRecording.setDisable(false);
            stopRecording.setDisable(true);
            return;
        }

        status.setText("Recording started. Gesture feedback is visible live.");

        startRecording.setDisable(true);
        stopRecording.setDisable(false);
    }


    private List<String> buildRecordingCommand(String videoDeviceName, String audioDeviceName, String videoPath) {
        String safeVideoName = videoDeviceName.replace("\"", "\\\"");
        String safeAudioName = audioDeviceName.replace("\"", "\\\"");
        String device = "video=\"" + safeVideoName + "\":audio=\"" + safeAudioName + "\"";

        return List.of(
                "ffmpeg",
                "-y",
                "-f", "dshow",
                "-rtbufsize", "256M",
                "-i", device,
                "-r", "30",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                videoPath
        );
    }

    private boolean startFfmpegRecording(List<String> command) {
        cleanupFfmpegHandles();
        recentFfmpegLogs.clear();

        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(true);

        try {
            ffmpegProcess = pb.start();
            Process processRef = ffmpegProcess;

            ffmpegStdin = new BufferedWriter(
                    new OutputStreamWriter(processRef.getOutputStream(), StandardCharsets.UTF_8)
            );

            ffmpegLogThread = new Thread(() -> {
                try (BufferedReader br = new BufferedReader(
                        new InputStreamReader(processRef.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        System.out.println("[ffmpeg] " + line);
                        synchronized (recentFfmpegLogs) {
                            recentFfmpegLogs.add(line);
                            if (recentFfmpegLogs.size() > 80) {
                                recentFfmpegLogs.remove(0);
                            }
                        }
                    }
                } catch (IOException ignored) {
                }
            }, "ffmpeg-log-drain");
            ffmpegLogThread.setDaemon(true);
            ffmpegLogThread.start();

            Thread.sleep(1200);
            if (!processRef.isAlive()) {
                List<String> tail;
                synchronized (recentFfmpegLogs) {
                    tail = new ArrayList<>(recentFfmpegLogs);
                }
                System.out.println("[ffmpeg] Recording process exited early. logs=" + String.join(" | ", tail));
                cleanupFfmpegHandles();
                return false;
            }

            return true;
        } catch (Exception e) {
            e.printStackTrace();
            cleanupFfmpegHandles();
            return false;
        }
    }

    @FXML
    protected void stopRecordingOnClick() {
        if (!isRecording) return;
        isRecording = false;

        status.setText("Stopping recording...");
        startRecording.setDisable(true);
        stopRecording.setDisable(true);

        Process process = ffmpegProcess;
        BufferedWriter stdin = ffmpegStdin;
        cleanupFfmpegHandles();

        if (process == null) {
            status.setText("No active recording process.");
            startRecording.setDisable(false);
            return;
        }

        Thread finalizeThread = new Thread(() -> finalizeRecordingAndStartPipeline(process, stdin), "recording-finalizer");
        finalizeThread.setDaemon(true);
        finalizeThread.start();
    }

    private void finalizeRecordingAndStartPipeline(Process process, BufferedWriter stdin) {
        try {
            if (process.isAlive() && stdin != null) {
                stdin.write("q\n");
                stdin.flush();
            }

            boolean exited = process.waitFor(20, TimeUnit.SECONDS);
            int exitCode = exited ? process.exitValue() : Integer.MIN_VALUE;
            if (!exited && process.isAlive()) {
                Platform.runLater(() -> status.setText("Finalizing recording took too long; forcing stop..."));
                process.destroyForcibly();
                process.waitFor(3, TimeUnit.SECONDS);
            }

            if (process.isAlive()) {
                Platform.runLater(() -> {
                    status.setText("Recording stop timed out; process may still be alive.");
                    startRecording.setDisable(false);
                    stopRecording.setDisable(true);
                });
                return;
            }

            notifyPythonRecordingStop();
            stopLiveFeedbackStream();
            Path recordedVideo = Path.of(currentSessionPath).resolve("video.mp4");
            if (!waitForRecordedVideoReady(recordedVideo, exitCode)) {
                Platform.runLater(() -> {
                    status.setText("Recording stopped, but video file is incomplete. Please record again.");
                    startRecording.setDisable(false);
                    stopRecording.setDisable(true);
                });
                return;
            }

            Platform.runLater(() -> status.setText("Recording stopped. Rendering harmonized output..."));
            runPostProcessingPipeline();

        } catch (Exception e) {
            e.printStackTrace();
            Platform.runLater(() -> {
                status.setText("Error stopping recording: " + e.getMessage());
                startRecording.setDisable(false);
                stopRecording.setDisable(true);
            });
        } finally {
            if (stdin != null) {
                try {
                    stdin.close();
                } catch (IOException ignored) {
                }
            }
        }
    }


    private boolean waitForRecordedVideoReady(Path recordedVideo, int recordingExitCode) {
        if (!Files.exists(recordedVideo)) {
            return false;
        }

        if (recordingExitCode == 0) {
            try {
                long size = Files.size(recordedVideo);
                if (size > 4096) {
                    return true;
                }
            } catch (IOException ignored) {
            }
        }

        long deadline = System.currentTimeMillis() + 15000;
        long lastSize = -1;
        int stableCount = 0;

        while (System.currentTimeMillis() < deadline) {
            if (isVideoContainerReadable(recordedVideo)) {
                return true;
            }

            try {
                long currentSize = Files.exists(recordedVideo) ? Files.size(recordedVideo) : -1;
                if (currentSize > 4096 && currentSize == lastSize) {
                    stableCount++;
                    if (stableCount >= 2) {
                        return true;
                    }
                } else {
                    stableCount = 0;
                }
                lastSize = currentSize;

                Thread.sleep(500);
            } catch (Exception e) {
                return false;
            }
        }

        return isVideoContainerReadable(recordedVideo) || stableCount >= 2;
    }

    private boolean isVideoContainerReadable(Path recordedVideo) {
        try {
            if (!Files.exists(recordedVideo) || Files.size(recordedVideo) < 1024) {
                return false;
            }
        } catch (IOException e) {
            return false;
        }

        if (runDurationProbe(new ProcessBuilder(
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                recordedVideo.toString()
        ))) {
            return true;
        }

        return runDurationProbe(new ProcessBuilder(
                "ffmpeg",
                "-v", "error",
                "-i", recordedVideo.toString(),
                "-f", "null",
                "-"
        ));
    }

    private boolean runDurationProbe(ProcessBuilder pb) {
        pb.redirectErrorStream(true);

        try {
            Process process = pb.start();
            String output;
            try (BufferedReader br = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                output = br.readLine();
            }

            boolean exited = process.waitFor(3, TimeUnit.SECONDS);
            if (!exited) {
                process.destroyForcibly();
                return false;
            }

            if (process.exitValue() != 0) {
                return false;
            }

            if (output == null || output.isBlank()) {
                return true;
            }

            try {
                return Double.parseDouble(output.trim()) > 0.0;
            } catch (NumberFormatException ignored) {
                return true;
            }
        } catch (Exception ignored) {
            return false;
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
        if (currentSessionPath != null) {
            command.add("--session-path");
            command.add(currentSessionPath);
        }

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

            if (!waitForLiveFeedbackEndpoint()) {
                status.setText("Live feedback stream did not become ready.");
                return false;
            }

            Platform.runLater(() -> {
                stopPreviewPlayer();
                outputMediaView.setVisible(false);
                outputMediaView.setManaged(false);
                feedbackImageView.setVisible(true);
                feedbackImageView.setManaged(true);
                previewPlaceholder.setVisible(false);
                previewPlaceholder.setManaged(false);
            });

            startFeedbackFramePolling();
            return true;
        } catch (Exception e) {
            e.printStackTrace();
            status.setText("Failed to launch Python live feedback stream.");
            return false;
        }
    }


    private boolean waitForLiveFeedbackEndpoint() {
        long deadline = System.currentTimeMillis() + 8000;

        while (System.currentTimeMillis() < deadline) {
            if (cameraStreamProcess == null || !cameraStreamProcess.isAlive()) {
                return false;
            }

            HttpURLConnection connection = null;
            try {
                URL url = new URL("http://127.0.0.1:" + CAMERA_STREAM_PORT + "/health");
                connection = (HttpURLConnection) url.openConnection();
                connection.setConnectTimeout(500);
                connection.setReadTimeout(500);
                int code = connection.getResponseCode();
                if (code == 200) {
                    return true;
                }
            } catch (IOException ignored) {
            } finally {
                if (connection != null) {
                    connection.disconnect();
                }
            }

            try {
                Thread.sleep(250);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return false;
            }
        }

        return false;
    }

    private void notifyPythonRecordingStart() {
        triggerPythonRecordingEndpoint("/record/start");
    }

    private void notifyPythonRecordingStop() {
        triggerPythonRecordingEndpoint("/record/stop");
    }

    private void triggerPythonRecordingEndpoint(String endpoint) {
        HttpURLConnection connection = null;
        try {
            URL url = new URL("http://127.0.0.1:" + CAMERA_STREAM_PORT + endpoint);
            connection = (HttpURLConnection) url.openConnection();
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(1000);
            connection.setReadTimeout(1000);
            connection.setDoOutput(true);
            connection.getOutputStream().write(new byte[0]);
            connection.getResponseCode();
        } catch (IOException e) {
            System.out.println("[live_gesture] endpoint call failed " + endpoint + ": " + e.getMessage());
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
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
        stopFeedbackFramePolling();
        Platform.runLater(() -> feedbackImageView.setImage(null));
    }


    private void startFeedbackFramePolling() {
        stopFeedbackFramePolling();

        feedbackFramePoller = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread thread = new Thread(r, "feedback-frame-poller");
            thread.setDaemon(true);
            return thread;
        });

        feedbackFramePoller.scheduleAtFixedRate(() -> {
            Process streamProcess = cameraStreamProcess;
            if (streamProcess == null || !streamProcess.isAlive()) {
                return;
            }

            HttpURLConnection connection = null;
            try {
                URL frameUrl = new URL("http://127.0.0.1:" + CAMERA_STREAM_PORT + "/frame?ts=" + System.nanoTime());
                connection = (HttpURLConnection) frameUrl.openConnection();
                connection.setConnectTimeout(600);
                connection.setReadTimeout(1200);
                connection.setUseCaches(false);

                try (InputStream inputStream = connection.getInputStream()) {
                    Image frameImage = new Image(inputStream);
                    if (!frameImage.isError()) {
                        Platform.runLater(() -> feedbackImageView.setImage(frameImage));
                    }
                }
            } catch (IOException ignored) {
            } finally {
                if (connection != null) {
                    connection.disconnect();
                }
            }
        }, 0, 120, TimeUnit.MILLISECONDS);
    }

    private void stopFeedbackFramePolling() {
        ScheduledExecutorService poller = feedbackFramePoller;
        feedbackFramePoller = null;
        if (poller != null) {
            poller.shutdownNow();
        }
    }

    private void runPostProcessingPipeline() {
        showProcessingOverlay();

        Thread pipelineThread = new Thread(() -> {
            try {
                Path sessionDir = Path.of(currentSessionPath);

                updateProcessingMessage("Validating real-time timeline...");
                ensureFileExists(sessionDir.resolve("timeline.json"), "Timeline was not generated during recording");

                updateProcessingMessage("Extracting clean audio for harmony blending...");
                String extractedWav = new FfmpegUtils().extractWav(currentSessionPath);
                if (extractedWav == null) {
                    throw new IOException("Audio extraction failed: output.wav was not created.");
                }
                ensureFileExists(Path.of(extractedWav), "Extracted wav file missing");

                updateProcessingMessage("Generating harmonized audio...");
                new PythonRunner().runHarmonizeAudio(currentSessionPath);
                Path harmonizedAudio = resolveHarmonizedAudio(sessionDir);
                ensureFileExists(harmonizedAudio, "Harmonized audio was not generated");

                updateProcessingMessage("Merging recorded video with harmonized audio...");
                Path outputVideo = muxFinalVideo(sessionDir);
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
                    status.setText("Background processing failed: " + e.getMessage());
                });
                e.printStackTrace();
            }
        }, "post-process-pipeline");

        pipelineThread.setDaemon(true);
        pipelineThread.start();
    }


    private void ensureFileExists(Path path, String message) throws IOException {
        if (!Files.exists(path) || Files.size(path) == 0) {
            throw new IOException(message + ": " + path);
        }
    }

    private Path muxFinalVideo(Path sessionDir) throws IOException, InterruptedException {
        Path inputVideo = sessionDir.resolve("video.mp4");
        Path harmonizedAudio = resolveHarmonizedAudio(sessionDir);
        Path finalVideo = sessionDir.resolve("harmonized_video.mp4");

        if (!Files.exists(inputVideo)) {
            throw new IOException("Recorded video not found: " + inputVideo);
        }

        List<String> copyMuxCommand = List.of(
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

        FfmpegRunResult copyResult = runFfmpeg(copyMuxCommand, "ffmpeg-mux-copy");
        if (copyResult.exitCode == 0 && Files.exists(finalVideo)) {
            return finalVideo;
        }

        System.out.println("[ffmpeg-mux] Copy mux failed, retrying with video re-encode...");

        List<String> transcodeMuxCommand = List.of(
                "ffmpeg", "-y",
                "-i", inputVideo.toString(),
                "-i", harmonizedAudio.toString(),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-shortest",
                finalVideo.toString()
        );

        FfmpegRunResult transcodeResult = runFfmpeg(transcodeMuxCommand, "ffmpeg-mux-transcode");
        if (transcodeResult.exitCode != 0 || !Files.exists(finalVideo)) {
            String copyTail = copyResult.recentLogs.stream().collect(Collectors.joining(" | "));
            String transcodeTail = transcodeResult.recentLogs.stream().collect(Collectors.joining(" | "));
            throw new IOException("Failed to build harmonized video preview. copyExit=" + copyResult.exitCode
                    + ", transcodeExit=" + transcodeResult.exitCode
                    + ", copyLogs=" + copyTail
                    + ", transcodeLogs=" + transcodeTail);
        }

        return finalVideo;
    }

    private Path resolveHarmonizedAudio(Path sessionDir) throws IOException {
        List<Path> candidates = List.of(
                sessionDir.resolve("harmonized_enhanced.wav"),
                sessionDir.resolve("harmonized.wav"),
                sessionDir.resolve("output.wav")
        );

        for (Path candidate : candidates) {
            if (Files.exists(candidate) && Files.size(candidate) > 0) {
                return candidate;
            }
        }

        throw new IOException("No harmonized audio file found. Expected one of: " + candidates);
    }

    private FfmpegRunResult runFfmpeg(List<String> command, String tag) throws IOException, InterruptedException {
        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(true);
        Process process = pb.start();

        List<String> recentLogs = new ArrayList<>();
        try (BufferedReader br = new BufferedReader(new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = br.readLine()) != null) {
                System.out.println("[" + tag + "] " + line);
                recentLogs.add(line);
                if (recentLogs.size() > 40) {
                    recentLogs.remove(0);
                }
            }
        }

        int exit = process.waitFor();
        return new FfmpegRunResult(exit, recentLogs);
    }

    private static class FfmpegRunResult {
        private final int exitCode;
        private final List<String> recentLogs;

        private FfmpegRunResult(int exitCode, List<String> recentLogs) {
            this.exitCode = exitCode;
            this.recentLogs = recentLogs;
        }
    }

    private void showVideoPreview(Path videoPath) {
        stopPreviewPlayer();

        feedbackImageView.setVisible(false);
        feedbackImageView.setManaged(false);
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
        feedbackImageView.setVisible(false);
        feedbackImageView.setManaged(false);

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
