package com.harmony.gestureharmonytoolui;

import javafx.application.Platform;
import javafx.fxml.FXML;
import javafx.scene.control.*;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.VBox;
import javafx.embed.swing.SwingNode;

import nu.pattern.OpenCV;
import org.opencv.core.Mat;
import org.opencv.imgproc.Imgproc;
import org.opencv.videoio.VideoCapture;

import javax.swing.*;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.awt.image.DataBufferByte;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;


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

    @FXML private ComboBox<MediaDevice> videoDeviceComboBox;
    @FXML private ComboBox<MediaDevice> audioDeviceComboBox;

    @FXML private SwingNode cameraSwingNode;

    private JPanel cameraPanel;
    private volatile BufferedImage currentFrame;
    private volatile VideoCapture videoCapture;
    private Thread captureThread;
    private Timer repaintTimer;
    private final AtomicBoolean cameraRunning = new AtomicBoolean(false);
    private static volatile boolean openCvLoaded = false;

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
        initializeSwingCameraPanel();
        loadHardwareDevices();
        hideProcessingOverlay();

        videoDeviceComboBox.valueProperty().addListener((obs, oldDevice, newDevice) -> {
            if (newDevice != null && currentSessionPath != null && !isRecording) {
                startCamera();
            }
        });
    }

    private void initializeSwingCameraPanel() {
        SwingUtilities.invokeLater(() -> {
            cameraPanel = new JPanel() {
                @Override
                protected void paintComponent(Graphics g) {
                    super.paintComponent(g);
                    BufferedImage frame = currentFrame;
                    if (frame == null) {
                        return;
                    }

                    Graphics2D g2 = (Graphics2D) g.create();
                    g2.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);

                    int panelW = getWidth();
                    int panelH = getHeight();
                    int imageW = frame.getWidth();
                    int imageH = frame.getHeight();

                    double scale = Math.min((double) panelW / imageW, (double) panelH / imageH);
                    int drawW = (int) (imageW * scale);
                    int drawH = (int) (imageH * scale);
                    int x = (panelW - drawW) / 2;
                    int y = (panelH - drawH) / 2;

                    g2.drawImage(frame, x + drawW, y, -drawW, drawH, null);
                    g2.dispose();
                }
            };

            cameraPanel.setDoubleBuffered(true);
            cameraPanel.setBackground(new Color(2, 6, 23));
            cameraSwingNode.setContent(cameraPanel);
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

        startCamera();
    }

    private void cleanupFfmpegHandles() {
        ffmpegProcess = null;
        ffmpegStdin = null;
        ffmpegLogThread = null;
    }

    public void startCamera() {
        if (cameraRunning.get()) {
            stopCamera();
        }

        if (!loadOpenCvLibrary()) {
            Platform.runLater(() -> status.setText("OpenCV native library failed to load."));
            return;
        }

        // Requirement: use VideoCapture(0) for native desktop camera capture.
        VideoCapture capture = new VideoCapture(0);

        if (!capture.isOpened()) {
            capture.release();
            Platform.runLater(() -> {
                status.setText("Unable to open camera via OpenCV VideoCapture(0).");
                previewPlaceholder.setVisible(true);
                previewPlaceholder.setManaged(true);
                cameraSwingNode.setVisible(false);
                cameraSwingNode.setManaged(false);
            });
            return;
        }

        videoCapture = capture;
        cameraRunning.set(true);

        Platform.runLater(() -> {
            cameraSwingNode.setVisible(true);
            cameraSwingNode.setManaged(true);
            previewPlaceholder.setVisible(false);
            previewPlaceholder.setManaged(false);
            status.setText("Session ready. Live camera preview is active.");
        });

        startSwingRepaintLoop();

        captureThread = new Thread(() -> {
            Mat frame = new Mat();
            Mat bgrFrame = new Mat();

            while (cameraRunning.get() && videoCapture != null && videoCapture.isOpened()) {
                if (!videoCapture.read(frame) || frame.empty()) {
                    continue;
                }

                if (frame.channels() == 1) {
                    Imgproc.cvtColor(frame, bgrFrame, Imgproc.COLOR_GRAY2BGR);
                } else if (frame.channels() == 4) {
                    Imgproc.cvtColor(frame, bgrFrame, Imgproc.COLOR_BGRA2BGR);
                } else {
                    frame.copyTo(bgrFrame);
                }

                currentFrame = matToBufferedImage(bgrFrame);
            }

            frame.release();
            bgrFrame.release();
        }, "opencv-camera-capture");

        captureThread.setDaemon(true);
        captureThread.start();
    }

    private void startSwingRepaintLoop() {
        SwingUtilities.invokeLater(() -> {
            if (repaintTimer != null && repaintTimer.isRunning()) {
                repaintTimer.stop();
            }

            repaintTimer = new Timer(16, e -> {
                if (cameraPanel != null) {
                    cameraPanel.repaint();
                }
            });
            repaintTimer.setCoalesce(true);
            repaintTimer.start();
        });
    }

    private BufferedImage matToBufferedImage(Mat mat) {
        int width = mat.width();
        int height = mat.height();
        int channels = mat.channels();

        byte[] sourcePixels = new byte[width * height * channels];
        mat.get(0, 0, sourcePixels);

        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_3BYTE_BGR);
        byte[] targetPixels = ((DataBufferByte) image.getRaster().getDataBuffer()).getData();
        System.arraycopy(sourcePixels, 0, targetPixels, 0, Math.min(sourcePixels.length, targetPixels.length));
        return image;
    }

    private boolean loadOpenCvLibrary() {
        if (openCvLoaded) {
            return true;
        }

        synchronized (HarmonyController.class) {
            if (openCvLoaded) {
                return true;
            }

            try {
                OpenCV.loadLocally();
                openCvLoaded = true;
                return true;
            } catch (Throwable t) {
                t.printStackTrace();
                return false;
            }
        }
    }

    public void stopCamera() {
        cameraRunning.set(false);

        Thread localCaptureThread = captureThread;
        if (localCaptureThread != null && localCaptureThread.isAlive()) {
            try {
                localCaptureThread.join(300);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        captureThread = null;

        VideoCapture capture = videoCapture;
        if (capture != null) {
            capture.release();
        }
        videoCapture = null;

        currentFrame = null;

        SwingUtilities.invokeLater(() -> {
            if (repaintTimer != null) {
                repaintTimer.stop();
                repaintTimer = null;
            }
            if (cameraPanel != null) {
                cameraPanel.repaint();
            }
        });
    }

    public void shutdown() {
        stopCamera();
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
