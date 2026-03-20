package com.harmony.gestureharmonytoolui;

import javafx.animation.AnimationTimer;
import javafx.application.Platform;
import javafx.fxml.FXML;
import javafx.scene.control.Button;
import javafx.scene.control.ButtonBar;
import javafx.scene.control.ButtonType;
import javafx.scene.control.ComboBox;
import javafx.scene.control.Dialog;
import javafx.scene.control.Label;
import javafx.scene.control.ListCell;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.Pane;
import javafx.scene.media.Media;
import javafx.scene.media.MediaPlayer;
import javafx.scene.media.MediaView;
import javafx.scene.paint.Color;
import javafx.scene.paint.CycleMethod;
import javafx.scene.paint.RadialGradient;
import javafx.scene.paint.Stop;
import javafx.scene.shape.Circle;
import javafx.scene.effect.DropShadow;
import javafx.stage.DirectoryChooser;
import javafx.stage.Window;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class HarmonyController {

    private static final String GESTURE_GUIDE = "Gestures: 1 finger = 1, 2 fingers = 2m, 3 fingers = 3m, 4 fingers = 4.";
    private static final String MANUAL_CHORDS_CONFIG = "chord_preferences.json";
    private static final List<String> GESTURE_CODES = List.of("ONE", "TWO_MINOR", "THREE_MINOR", "FOUR");
    private static final int PLACEHOLDER_WIDTH = 900;
    private static final int PLACEHOLDER_HEIGHT = 500;

    private String currentSessionPath;
    private boolean isRecording;
    private boolean isProcessing;
    private Process ffmpegProcess;
    private BufferedWriter ffmpegStdin;
    private Thread ffmpegLogThread;
    private final List<String> recentFfmpegLogs = Collections.synchronizedList(new ArrayList<>());

    private Process cameraStreamProcess;
    private Thread cameraStreamLogThread;
    private OutputStream cameraStreamStdin;

    private MediaPlayer previewMediaPlayer;
    private Path harmonizedVideoPath;
    private AnimationTimer placeholderAnimationTimer;
    private long placeholderAnimationStartNanos = -1L;
    private final List<Circle> placeholderParticles = new ArrayList<>();
    private final List<PlaceholderParticleMotion> placeholderParticleMotions = new ArrayList<>();
    private boolean manualChordSelectionsTouched;

    @FXML private Label sessionLabel;
    @FXML private Label status;
    @FXML private Label processingMessage;
    @FXML private Button startRecording;
    @FXML private Button stopRecording;
    @FXML private Button cancelRecording;
    @FXML private Button saveVideoButton;
    @FXML private Button playPauseButton;
    @FXML private Button replayButton;
    @FXML private javafx.scene.layout.VBox processingOverlay;
    @FXML private javafx.scene.layout.HBox previewActions;

    @FXML private ComboBox<MediaDevice> videoDeviceComboBox;
    @FXML private ComboBox<MediaDevice> audioDeviceComboBox;

    @FXML private Pane placeholderPane;
    @FXML private MediaView outputMediaView;

    private enum ChordMode {
        AUTOMATIC,
        MANUAL
    }

    private record ChordOption(String label, int rootSemitone, List<Integer> intervals) {
        @Override
        public String toString() {
            return label;
        }
    }

    private record ChordQuality(String label, List<Integer> intervals) {
    }

    private record KeyOption(String label, int rootNote, String scaleType) {
        @Override
        public String toString() {
            return label;
        }
    }

    private record RecordingChordConfig(ChordMode mode, KeyOption key, Map<String, ChordOption> mappings) {
    }

    private record PlaceholderParticleMotion(
            double amplitudeX,
            double amplitudeY,
            double frequencyX,
            double frequencyY,
            double phase,
            double driftX,
            double driftY
    ) {
    }

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
        loadPlaceholderImage();
        loadHardwareDevices();
        hideProcessingOverlay();
        showPlaceholderImage();
        previewActions.setVisible(false);
        previewActions.setManaged(false);
        sessionLabel.setText(GESTURE_GUIDE + " Recording captures the gesture-feedback window output.");
    }

    private void loadPlaceholderImage() {
        placeholderPane.setPrefSize(PLACEHOLDER_WIDTH, PLACEHOLDER_HEIGHT);
        placeholderPane.setMinSize(PLACEHOLDER_WIDTH, PLACEHOLDER_HEIGHT);
        placeholderPane.setMaxSize(PLACEHOLDER_WIDTH, PLACEHOLDER_HEIGHT);
        placeholderPane.getChildren().clear();
        placeholderParticles.clear();
        placeholderParticleMotions.clear();

        createPlaceholderParticles();
        updatePlaceholderAnimation(0.0);
        startPlaceholderAnimation();
    }

    private void startPlaceholderAnimation() {
        if (placeholderAnimationTimer != null) {
            return;
        }

        placeholderAnimationTimer = new AnimationTimer() {
            @Override
            public void handle(long now) {
                if (placeholderAnimationStartNanos < 0L) {
                    placeholderAnimationStartNanos = now;
                }
                double elapsedSeconds = (now - placeholderAnimationStartNanos) / 1_000_000_000.0;
                if (placeholderPane.isVisible()) {
                    updatePlaceholderAnimation(elapsedSeconds);
                }
            }
        };
        placeholderAnimationTimer.start();
    }

    private void createPlaceholderParticles() {
        Color[] palette = {
                Color.web("#22d3ee", 0.90),
                Color.web("#38bdf8", 0.88),
                Color.web("#818cf8", 0.82),
                Color.web("#a78bfa", 0.80),
                Color.web("#f472b6", 0.76),
                Color.web("#f8fafc", 0.68)
        };

        double[][] motionPresets = {
                {180, 84, 0.58, 0.34, 0.4, 0.12, -0.06},
                {210, 118, 0.42, 0.49, 1.1, -0.08, 0.07},
                {260, 96, 0.63, 0.28, 1.9, 0.05, 0.10},
                {150, 132, 0.55, 0.41, 2.6, -0.11, 0.04},
                {310, 74, 0.36, 0.60, 3.1, 0.10, -0.09},
                {230, 144, 0.47, 0.37, 3.8, -0.06, -0.05},
                {125, 88, 0.79, 0.52, 4.4, 0.08, 0.03},
                {280, 108, 0.31, 0.45, 5.0, -0.04, 0.08},
                {190, 68, 0.67, 0.33, 5.6, 0.06, -0.02},
                {340, 152, 0.28, 0.22, 6.2, -0.03, 0.06}
        };

        for (int i = 0; i < motionPresets.length; i++) {
            double radius = 10 + (i % 4) * 4;
            Color color = palette[i % palette.length];
            Circle particle = new Circle(radius);
            particle.setManaged(false);
            particle.setMouseTransparent(true);
            particle.setFill(new RadialGradient(
                    0,
                    0,
                    0.35,
                    0.35,
                    1,
                    true,
                    CycleMethod.NO_CYCLE,
                    new Stop(0.0, color),
                    new Stop(0.45, color.deriveColor(0, 1, 1, 0.55)),
                    new Stop(1.0, Color.TRANSPARENT)
            ));
            particle.setEffect(new DropShadow(radius * 1.35, color.deriveColor(0, 1, 1, 0.45)));

            placeholderParticles.add(particle);
            placeholderParticleMotions.add(new PlaceholderParticleMotion(
                    motionPresets[i][0],
                    motionPresets[i][1],
                    motionPresets[i][2],
                    motionPresets[i][3],
                    motionPresets[i][4],
                    motionPresets[i][5],
                    motionPresets[i][6]
            ));
            placeholderPane.getChildren().add(particle);
        }
    }

    private void updatePlaceholderAnimation(double timeSeconds) {
        double centerX = PLACEHOLDER_WIDTH * 0.5;
        double centerY = PLACEHOLDER_HEIGHT * 0.5;
        double time = timeSeconds * 0.92;

        for (int i = 0; i < placeholderParticles.size(); i++) {
            Circle particle = placeholderParticles.get(i);
            PlaceholderParticleMotion motion = placeholderParticleMotions.get(i);

            double x = centerX
                    + Math.sin(time * motion.frequencyX() + motion.phase()) * motion.amplitudeX()
                    + Math.cos(time * (motion.frequencyY() * 0.72) - motion.phase()) * 42
                    + Math.sin(time * 0.22 + (i * 0.4)) * (PLACEHOLDER_WIDTH * motion.driftX());
            double y = centerY
                    + Math.cos(time * motion.frequencyY() + motion.phase()) * motion.amplitudeY()
                    + Math.sin(time * (motion.frequencyX() * 0.68) + motion.phase()) * 28
                    + Math.cos(time * 0.18 + (i * 0.35)) * (PLACEHOLDER_HEIGHT * motion.driftY());

            particle.setCenterX(x);
            particle.setCenterY(y);
            particle.setOpacity(0.38 + 0.28 * (0.5 + 0.5 * Math.sin(time * 0.9 + motion.phase())));
        }
    }

    private void loadHardwareDevices() {
        status.setText("Loading hardware devices...");
        startRecording.setDisable(true);

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

                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8)
                )) {
                    String line;
                    MediaDevice currentDevice = null;
                    final int sectionNone = 0;
                    final int sectionVideo = 1;
                    final int sectionAudio = 2;
                    int currentSection = sectionNone;

                    while ((line = reader.readLine()) != null) {
                        System.out.println("[Device Scan] " + line);
                        String lowerLine = line.toLowerCase();

                        if (lowerLine.contains("directshow video devices") || lowerLine.contains("video devices")) {
                            currentSection = sectionVideo;
                            currentDevice = null;
                            continue;
                        }
                        if (lowerLine.contains("directshow audio devices") || lowerLine.contains("audio devices")) {
                            currentSection = sectionAudio;
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

                        if (currentSection == sectionVideo) {
                            if (seenVideoNames.add(extractedName)) {
                                currentDevice = new MediaDevice(extractedName);
                                videoDevices.add(currentDevice);
                            }
                        } else if (currentSection == sectionAudio) {
                            if (seenAudioNames.add(extractedName)) {
                                currentDevice = new MediaDevice(extractedName);
                                audioDevices.add(currentDevice);
                            }
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

                boolean ready = !videoDevices.isEmpty() && !audioDevices.isEmpty();
                startRecording.setDisable(!ready);
                status.setText(ready
                        ? "Devices loaded. Choose a camera and microphone, then click Start Recording."
                        : "No usable camera/microphone pair was found.");
            });

        }, "device-loader").start();
    }

    private Optional<RecordingChordConfig> promptForRecordingChordConfig() {
        ButtonType automaticButton = new ButtonType("Automatic", ButtonBar.ButtonData.OK_DONE);
        ButtonType manualButton = new ButtonType("Manual", ButtonBar.ButtonData.OTHER);
        ButtonType cancelButton = new ButtonType("Cancel", ButtonBar.ButtonData.CANCEL_CLOSE);

        Dialog<ButtonType> modeDialog = new Dialog<>();
        modeDialog.setTitle("Choose chord workflow");
        modeDialog.setHeaderText("How should the harmony chords be prepared for this take?");
        modeDialog.getDialogPane().setContent(new Label(
                "Automatic keeps the current key-detection logic.\n"
                        + "Manual lets you choose the key and the four gesture-to-chord mappings before recording starts."
        ));
        modeDialog.getDialogPane().getButtonTypes().addAll(automaticButton, manualButton, cancelButton);

        Optional<ButtonType> result = modeDialog.showAndWait();
        if (result.isEmpty() || result.get() == cancelButton) {
            return Optional.empty();
        }
        if (result.get() == automaticButton) {
            return Optional.of(new RecordingChordConfig(ChordMode.AUTOMATIC, null, Map.of()));
        }

        return showManualChordDialog();
    }

    private Optional<RecordingChordConfig> showManualChordDialog() {
        Dialog<RecordingChordConfig> dialog = new Dialog<>();
        dialog.setTitle("Manual chord setup");
        dialog.setHeaderText("Choose the song key and the four gesture chord mappings.");

        ButtonType confirmButton = new ButtonType("Use Manual Mapping", ButtonBar.ButtonData.OK_DONE);
        dialog.getDialogPane().getButtonTypes().addAll(confirmButton, ButtonType.CANCEL);

        ComboBox<KeyOption> keyComboBox = new ComboBox<>();
        keyComboBox.getItems().setAll(buildKeyOptions());
        keyComboBox.getSelectionModel().selectFirst();
        keyComboBox.setPrefWidth(220);

        List<ChordOption> allChordOptions = buildAllChordOptions();
        Map<String, ComboBox<ChordOption>> mappingBoxes = new LinkedHashMap<>();
        GridPane grid = new GridPane();
        grid.setHgap(12);
        grid.setVgap(12);

        grid.add(new Label("Key"), 0, 0);
        grid.add(keyComboBox, 1, 0);

        int row = 1;
        for (String gestureCode : GESTURE_CODES) {
            ComboBox<ChordOption> comboBox = new ComboBox<>();
            comboBox.setPrefWidth(220);
            comboBox.setVisibleRowCount(14);
            comboBox.setCellFactory(listView -> new ListCell<>() {
                @Override
                protected void updateItem(ChordOption item, boolean empty) {
                    super.updateItem(item, empty);
                    setText(empty || item == null ? null : item.label());
                }
            });
            comboBox.setButtonCell(new ListCell<>() {
                @Override
                protected void updateItem(ChordOption item, boolean empty) {
                    super.updateItem(item, empty);
                    setText(empty || item == null ? null : item.label());
                }
            });
            comboBox.getItems().setAll(allChordOptions);
            comboBox.valueProperty().addListener((observable, oldValue, newValue) -> {
                if (newValue != null) {
                    manualChordSelectionsTouched = true;
                }
            });
            mappingBoxes.put(gestureCode, comboBox);
            grid.add(new Label(gesturePromptLabel(gestureCode)), 0, row);
            grid.add(comboBox, 1, row);
            row++;
        }

        manualChordSelectionsTouched = false;
        applyDefaultManualMappings(keyComboBox.getValue(), mappingBoxes, allChordOptions);
        manualChordSelectionsTouched = false;
        keyComboBox.valueProperty().addListener((observable, oldValue, newValue) -> {
            if (!manualChordSelectionsTouched) {
                applyDefaultManualMappings(newValue, mappingBoxes, allChordOptions);
                manualChordSelectionsTouched = false;
            }
        });

        dialog.getDialogPane().setContent(grid);
        dialog.setResultConverter(buttonType -> {
            if (buttonType != confirmButton) {
                return null;
            }

            KeyOption selectedKey = keyComboBox.getValue();
            if (selectedKey == null) {
                return null;
            }

            Map<String, ChordOption> mappings = new LinkedHashMap<>();
            for (String gestureCode : GESTURE_CODES) {
                ChordOption option = mappingBoxes.get(gestureCode).getValue();
                if (option == null) {
                    return null;
                }
                mappings.put(gestureCode, option);
            }
            return new RecordingChordConfig(ChordMode.MANUAL, selectedKey, mappings);
        });

        return dialog.showAndWait();
    }

    private List<KeyOption> buildKeyOptions() {
        String[] noteNames = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"};
        List<KeyOption> options = new ArrayList<>();
        for (int i = 0; i < noteNames.length; i++) {
            options.add(new KeyOption(noteNames[i] + " Major", 48 + i, "major"));
        }
        for (int i = 0; i < noteNames.length; i++) {
            options.add(new KeyOption(noteNames[i] + " Minor", 48 + i, "minor"));
        }
        return options;
    }

    private List<ChordOption> buildAllChordOptions() {
        List<ChordOption> options = new ArrayList<>();
        for (Map.Entry<String, Integer> rootEntry : buildChordRoots().entrySet()) {
            for (ChordQuality quality : buildChordQualities()) {
                options.add(new ChordOption(
                        rootEntry.getKey() + quality.label(),
                        rootEntry.getValue(),
                        quality.intervals()
                ));
            }
        }
        return options;
    }

    private Map<String, Integer> buildChordRoots() {
        Map<String, Integer> roots = new LinkedHashMap<>();
        roots.put("C", 0);
        roots.put("C#", 1);
        roots.put("Db", 1);
        roots.put("D", 2);
        roots.put("D#", 3);
        roots.put("Eb", 3);
        roots.put("E", 4);
        roots.put("F", 5);
        roots.put("F#", 6);
        roots.put("Gb", 6);
        roots.put("G", 7);
        roots.put("G#", 8);
        roots.put("Ab", 8);
        roots.put("A", 9);
        roots.put("A#", 10);
        roots.put("Bb", 10);
        roots.put("B", 11);
        return roots;
    }

    private List<ChordQuality> buildChordQualities() {
        return List.of(
                new ChordQuality(" major", List.of(0, 4, 7)),
                new ChordQuality(" minor", List.of(0, 3, 7)),
                new ChordQuality(" diminished", List.of(0, 3, 6)),
                new ChordQuality(" augmented", List.of(0, 4, 8)),
                new ChordQuality(" sus2", List.of(0, 2, 7)),
                new ChordQuality(" sus4", List.of(0, 5, 7)),
                new ChordQuality(" 5", List.of(0, 7)),
                new ChordQuality(" 6", List.of(0, 4, 7, 9)),
                new ChordQuality(" minor 6", List.of(0, 3, 7, 9)),
                new ChordQuality(" 7", List.of(0, 4, 7, 10)),
                new ChordQuality(" major 7", List.of(0, 4, 7, 11)),
                new ChordQuality(" minor 7", List.of(0, 3, 7, 10)),
                new ChordQuality(" minor-major 7", List.of(0, 3, 7, 11)),
                new ChordQuality(" diminished 7", List.of(0, 3, 6, 9)),
                new ChordQuality(" half-diminished 7", List.of(0, 3, 6, 10)),
                new ChordQuality(" add9", List.of(0, 4, 7, 14)),
                new ChordQuality(" minor add9", List.of(0, 3, 7, 14)),
                new ChordQuality(" 9", List.of(0, 4, 7, 10, 14)),
                new ChordQuality(" major 9", List.of(0, 4, 7, 11, 14)),
                new ChordQuality(" minor 9", List.of(0, 3, 7, 10, 14)),
                new ChordQuality(" 11", List.of(0, 4, 7, 10, 14, 17)),
                new ChordQuality(" minor 11", List.of(0, 3, 7, 10, 14, 17)),
                new ChordQuality(" 13", List.of(0, 4, 7, 10, 14, 17, 21)),
                new ChordQuality(" minor 13", List.of(0, 3, 7, 10, 14, 17, 21)),
                new ChordQuality(" 7sus2", List.of(0, 2, 7, 10)),
                new ChordQuality(" 7sus4", List.of(0, 5, 7, 10))
        );
    }

    private void applyDefaultManualMappings(
            KeyOption keyOption,
            Map<String, ComboBox<ChordOption>> mappingBoxes,
            List<ChordOption> allChordOptions
    ) {
        if (keyOption == null) {
            return;
        }

        int tonic = Math.floorMod(keyOption.rootNote() - 48, 12);
        boolean minor = "minor".equalsIgnoreCase(keyOption.scaleType());

        Map<String, ChordOption> defaults = new LinkedHashMap<>();
        defaults.put("ONE", findChordOption(allChordOptions, tonic, minor ? " minor" : " major"));
        defaults.put("TWO_MINOR", findChordOption(allChordOptions, tonic + 2, minor ? " diminished" : " minor"));
        defaults.put("THREE_MINOR", findChordOption(allChordOptions, tonic + (minor ? 3 : 4), minor ? " major" : " minor"));
        defaults.put("FOUR", findChordOption(allChordOptions, tonic + 5, minor ? " minor" : " major"));

        for (Map.Entry<String, ComboBox<ChordOption>> entry : mappingBoxes.entrySet()) {
            ChordOption option = defaults.get(entry.getKey());
            if (option != null) {
                entry.getValue().getSelectionModel().select(option);
            }
        }
    }

    private ChordOption findChordOption(List<ChordOption> options, int rootSemitone, String qualitySuffix) {
        return options.stream()
                .filter(option -> option.rootSemitone() == Math.floorMod(rootSemitone, 12))
                .filter(option -> option.label().endsWith(qualitySuffix))
                .findFirst()
                .orElse(options.getFirst());
    }

    private String gesturePromptLabel(String gestureCode) {
        return switch (gestureCode) {
            case "ONE" -> "1 finger";
            case "TWO_MINOR" -> "2 fingers";
            case "THREE_MINOR" -> "3 fingers";
            case "FOUR" -> "4 fingers";
            default -> gestureCode;
        };
    }

    private String summarizeManualSelection(RecordingChordConfig config) {
        if (config.key() == null || config.mappings().isEmpty()) {
            return "manual setup";
        }
        return config.key().label() + " | 1→" + config.mappings().get("ONE").label()
                + ", 2→" + config.mappings().get("TWO_MINOR").label()
                + ", 3→" + config.mappings().get("THREE_MINOR").label()
                + ", 4→" + config.mappings().get("FOUR").label();
    }

    private void persistChordPreferences(Path sessionDir, RecordingChordConfig config) throws IOException {
        StringBuilder json = new StringBuilder();
        json.append("{\n");
        json.append("  \"mode\": \"").append(config.mode().name().toLowerCase()).append("\"");

        if (config.mode() == ChordMode.MANUAL && config.key() != null) {
            json.append(",\n  \"key\": {\n");
            json.append("    \"label\": \"").append(escapeJson(config.key().label())).append("\",\n");
            json.append("    \"root_note\": ").append(config.key().rootNote()).append(",\n");
            json.append("    \"scale_type\": \"").append(escapeJson(config.key().scaleType())).append("\"\n");
            json.append("  },\n");
            json.append("  \"mappings\": {\n");

            int index = 0;
            for (String gestureCode : GESTURE_CODES) {
                ChordOption option = config.mappings().get(gestureCode);
                json.append("    \"").append(gestureCode).append("\": {\n");
                json.append("      \"label\": \"").append(escapeJson(option.label())).append("\",\n");
                json.append("      \"root_semitone\": ").append(option.rootSemitone()).append(",\n");
                json.append("      \"intervals\": [");
                for (int i = 0; i < option.intervals().size(); i++) {
                    if (i > 0) {
                        json.append(", ");
                    }
                    json.append(option.intervals().get(i));
                }
                json.append("]\n");
                json.append("    }");
                if (index < GESTURE_CODES.size() - 1) {
                    json.append(",");
                }
                json.append("\n");
                index++;
            }
            json.append("  }\n");
        } else {
            json.append("\n");
        }

        json.append("}\n");
        Files.writeString(sessionDir.resolve(MANUAL_CHORDS_CONFIG), json.toString(), StandardCharsets.UTF_8);
    }

    private String escapeJson(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private String extractBetweenQuotes(String text) {
        int start = text.indexOf('"');
        int end = text.lastIndexOf('"');
        if (start != -1 && end != -1 && start < end) {
            return text.substring(start + 1, end);
        }
        return null;
    }

    @FXML
    protected void startRecordingOnClick() {
        if (isRecording || isProcessing) {
            return;
        }

        MediaDevice selectedVideo = videoDeviceComboBox.getValue();
        MediaDevice selectedAudio = audioDeviceComboBox.getValue();

        if (selectedVideo == null || selectedAudio == null) {
            status.setText("Please select both a camera and a microphone.");
            return;
        }

        Optional<RecordingChordConfig> configSelection = promptForRecordingChordConfig();
        if (configSelection.isEmpty()) {
            status.setText("Recording canceled before the chord workflow was selected.");
            return;
        }
        RecordingChordConfig recordingChordConfig = configSelection.get();

        resetPreviewForNewCapture();
        currentSessionPath = SessionManager.createNewSession();
        sessionLabel.setText("Current session: " + currentSessionPath + "\n" + GESTURE_GUIDE + "\nChord mode: "
                + (recordingChordConfig.mode() == ChordMode.MANUAL
                ? "Manual — " + summarizeManualSelection(recordingChordConfig)
                : "Automatic detection"));

        Path sessionDir = Path.of(currentSessionPath);
        try {
            Files.createDirectories(sessionDir);
            persistChordPreferences(sessionDir, recordingChordConfig);
        } catch (IOException e) {
            status.setText("Failed to prepare the session chord settings.");
            deleteCurrentSessionQuietly();
            return;
        }

        if (!startLiveFeedbackStream()) {
            status.setText("Unable to start the gesture feedback pipeline.");
            deleteCurrentSessionQuietly();
            return;
        }

        isRecording = true;
        harmonizedVideoPath = null;

        String videoPath = sessionDir.resolve("video.mp4").toString();
        String primaryVideoName = selectedVideo.getAltName() != null ? selectedVideo.getAltName() : selectedVideo.toString();
        String primaryAudioName = selectedAudio.getAltName() != null ? selectedAudio.getAltName() : selectedAudio.toString();

        boolean started = startFfmpegRecording(buildRecordingCommand(primaryVideoName, primaryAudioName, videoPath), cameraStreamStdin);
        if (!started) {
            String fallbackVideo = selectedVideo.toString();
            String fallbackAudio = selectedAudio.toString();
            boolean hasDisplayNameFallback = !fallbackVideo.equals(primaryVideoName) || !fallbackAudio.equals(primaryAudioName);
            if (hasDisplayNameFallback) {
                status.setText("Retrying recording with device display names...");
                started = startFfmpegRecording(buildRecordingCommand(fallbackVideo, fallbackAudio, videoPath), cameraStreamStdin);
            }
        }

        if (!started) {
            status.setText("Retrying recording with fallback device index (0)...");
            started = startFfmpegRecording(buildRecordingCommand("0", "0", videoPath), cameraStreamStdin);
        }

        if (!started) {
            stopLiveFeedbackStream();
            deleteCurrentSessionQuietly();
            isRecording = false;
            startRecording.setDisable(false);
            stopRecording.setDisable(true);
            cancelRecording.setDisable(true);
            status.setText("Failed to start recording. Check the selected devices or ffmpeg logs.");
            return;
        }

        status.setText("Recording started. The gesture-feedback pipeline is now being captured.");
        startRecording.setDisable(true);
        stopRecording.setDisable(false);
        cancelRecording.setDisable(false);
    }

    private List<String> buildRecordingCommand(String videoDeviceName, String audioDeviceName, String videoPath) {
        String safeVideoName = videoDeviceName.replace("\"", "\\\"");
        String safeAudioName = audioDeviceName.replace("\"", "\\\"");
        String device = "video=\"" + safeVideoName + "\":audio=\"" + safeAudioName + "\"";

        return List.of(
                "ffmpeg",
                "-y",
                "-thread_queue_size", "4096",
                "-f", "dshow",
                "-framerate", "30",
                "-video_size", "1280x720",
                "-i", device,
                "-map", "0:v",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-c:a", "aac",
                "-movflags", "+faststart+frag_keyframe+empty_moov",
                videoPath,
                "-map", "0:v",
                "-an",
                "-vf", "fps=30",
                "-c:v", "mjpeg",
                "-q:v", "5",
                "-f", "mjpeg",
                "pipe:1"
        );
    }

    private boolean startFfmpegRecording(List<String> command, OutputStream previewSink) {
        cleanupFfmpegHandles();
        recentFfmpegLogs.clear();

        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(false);

        try {
            ffmpegProcess = pb.start();
            Process processRef = ffmpegProcess;

            ffmpegStdin = new BufferedWriter(
                    new OutputStreamWriter(processRef.getOutputStream(), StandardCharsets.UTF_8)
            );

            ffmpegLogThread = new Thread(() -> {
                try (BufferedReader br = new BufferedReader(
                        new InputStreamReader(processRef.getErrorStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        System.out.println("[ffmpeg] " + line);
                        synchronized (recentFfmpegLogs) {
                            recentFfmpegLogs.add(line);
                            if (recentFfmpegLogs.size() > 120) {
                                recentFfmpegLogs.remove(0);
                            }
                        }
                    }
                } catch (IOException ignored) {
                }
            }, "ffmpeg-log-drain");
            ffmpegLogThread.setDaemon(true);
            ffmpegLogThread.start();

            if (previewSink != null) {
                Thread previewPipeThread = new Thread(() -> {
                    try (InputStream in = processRef.getInputStream(); OutputStream out = previewSink) {
                        in.transferTo(out);
                    } catch (IOException ignored) {
                    }
                }, "ffmpeg-preview-pipe");
                previewPipeThread.setDaemon(true);
                previewPipeThread.start();
            }

            long deadline = System.currentTimeMillis() + 5000;
            while (System.currentTimeMillis() < deadline) {
                if (!processRef.isAlive()) {
                    break;
                }
                if (containsFfmpegFrameProgress()) {
                    return true;
                }
                Thread.sleep(150);
            }

            if (!processRef.isAlive()) {
                List<String> tail = snapshotFfmpegLogs();
                reportFfmpegStartupError(tail);
                cleanupFfmpegHandles();
                return false;
            }

            reportFfmpegStartupError(snapshotFfmpegLogs());
            cleanupFfmpegHandles();
            return false;
        } catch (Exception e) {
            e.printStackTrace();
            cleanupFfmpegHandles();
            return false;
        }
    }

    private boolean containsFfmpegFrameProgress() {
        synchronized (recentFfmpegLogs) {
            for (String line : recentFfmpegLogs) {
                if (line.contains("frame=") && !line.contains("frame=    0")) {
                    return true;
                }
            }
        }
        return false;
    }

    private List<String> snapshotFfmpegLogs() {
        synchronized (recentFfmpegLogs) {
            return new ArrayList<>(recentFfmpegLogs);
        }
    }

    private void reportFfmpegStartupError(List<String> logs) {
        String joined = String.join(" | ", logs).toLowerCase();
        if (joined.contains("device or resource busy") || joined.contains("resource busy")) {
            status.setText("Recording failed: camera/microphone is busy in another app.");
            return;
        }
        if (joined.contains("could not find") || joined.contains("no such device") || joined.contains("not found")) {
            status.setText("Recording failed: selected camera/microphone device not found.");
            return;
        }
        if (joined.contains("invalid argument") || joined.contains("invalid data found")) {
            status.setText("Recording failed: invalid device identifier or ffmpeg input format.");
        }
    }

    @FXML
    protected void stopRecordingOnClick() {
        if (!isRecording || currentSessionPath == null) {
            return;
        }

        isRecording = false;
        isProcessing = true;
        status.setText("Stopping recording and starting processing...");
        startRecording.setDisable(true);
        stopRecording.setDisable(true);
        cancelRecording.setDisable(true);
        showProcessingOverlay();

        Process process = ffmpegProcess;
        BufferedWriter stdin = ffmpegStdin;
        cleanupFfmpegHandles();

        if (process == null) {
            isProcessing = false;
            hideProcessingOverlay();
            status.setText("No active recording process was found.");
            startRecording.setDisable(false);
            return;
        }

        Thread finalizeThread = new Thread(() -> finalizeRecordingAndStartPipeline(process, stdin), "recording-finalizer");
        finalizeThread.setDaemon(true);
        finalizeThread.start();
    }

    @FXML
    protected void cancelRecordingOnClick() {
        if (!isRecording) {
            status.setText("There is no active recording to cancel.");
            return;
        }

        isRecording = false;
        isProcessing = false;
        status.setText("Recording canceled. Deleting the current session...");
        startRecording.setDisable(false);
        stopRecording.setDisable(true);
        cancelRecording.setDisable(true);
        hideProcessingOverlay();

        Process process = ffmpegProcess;
        cleanupFfmpegHandles();

        if (process != null && process.isAlive()) {
            process.destroyForcibly();
            try {
                process.waitFor(3, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        stopLiveFeedbackStream();
        deleteCurrentSessionQuietly();
        resetToIdleState("Recording canceled. The session files were deleted.");
    }

    @FXML
    protected void saveVideoOnClick() {
        if (harmonizedVideoPath == null || !Files.exists(harmonizedVideoPath)) {
            status.setText("No harmonized video is available to save.");
            return;
        }

        DirectoryChooser chooser = new DirectoryChooser();
        chooser.setTitle("Choose directory to save harmonized video");

        Window window = status.getScene() != null ? status.getScene().getWindow() : null;
        File selectedDir = chooser.showDialog(window);
        if (selectedDir == null) {
            status.setText("Save canceled.");
            return;
        }

        try {
            Path destination = selectedDir.toPath().resolve("harmonized_video.mp4");
            Files.copy(harmonizedVideoPath, destination, StandardCopyOption.REPLACE_EXISTING);
            status.setText("Saved harmonized video to " + destination + ".");
        } catch (IOException e) {
            status.setText("Failed to save harmonized video.");
        }
    }

    @FXML
    protected void playPauseOnClick() {
        if (previewMediaPlayer == null) {
            return;
        }

        MediaPlayer.Status playerStatus = previewMediaPlayer.getStatus();
        if (playerStatus == MediaPlayer.Status.PLAYING) {
            previewMediaPlayer.pause();
            playPauseButton.setText("Play");
        } else {
            previewMediaPlayer.play();
            playPauseButton.setText("Pause");
        }
    }

    @FXML
    protected void replayOnClick() {
        if (previewMediaPlayer == null) {
            return;
        }

        previewMediaPlayer.seek(javafx.util.Duration.ZERO);
        previewMediaPlayer.play();
        playPauseButton.setText("Pause");
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
                    isProcessing = false;
                    hideProcessingOverlay();
                    status.setText("Recording stop timed out; the process may still be alive.");
                    startRecording.setDisable(false);
                    stopRecording.setDisable(true);
                });
                return;
            }

            Path sessionDir = Path.of(currentSessionPath);
            Path recordedVideo = sessionDir.resolve("video.mp4");
            Path previewCapture = sessionDir.resolve("preview_capture.mp4");
            if (!waitForRecordedVideoReady(recordedVideo, exitCode) || !waitForPreviewCaptureReady(previewCapture)) {
                Platform.runLater(() -> {
                    isProcessing = false;
                    hideProcessingOverlay();
                    status.setText("Recording stopped, but the captured video is incomplete. Please record again.");
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
                isProcessing = false;
                hideProcessingOverlay();
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
            stopLiveFeedbackStream();
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

    private boolean waitForPreviewCaptureReady(Path previewCapture) {
        long deadline = System.currentTimeMillis() + 10000;
        while (System.currentTimeMillis() < deadline) {
            if (isVideoContainerReadable(previewCapture)) {
                return true;
            }
            try {
                Thread.sleep(400);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return isVideoContainerReadable(previewCapture);
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
        command.add("--preview");
        command.add("--session-path");
        command.add(currentSessionPath);

        ProcessBuilder pb = new ProcessBuilder(command);
        pb.redirectErrorStream(true);

        try {
            cameraStreamProcess = pb.start();
            cameraStreamStdin = cameraStreamProcess.getOutputStream();

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

            Thread.sleep(800);
            if (!isLiveFeedbackRunning()) {
                status.setText("Failed to launch the gesture feedback window.");
                return false;
            }

            Platform.runLater(this::showPlaceholderImage);
            return true;
        } catch (Exception e) {
            e.printStackTrace();
            status.setText("Failed to launch the Python preview process.");
            return false;
        }
    }

    private void stopLiveFeedbackStream() {
        Process process = cameraStreamProcess;
        OutputStream stdin = cameraStreamStdin;
        cameraStreamProcess = null;
        cameraStreamStdin = null;

        if (stdin != null) {
            try {
                stdin.close();
            } catch (IOException ignored) {
            }
        }

        if (process != null) {
            try {
                if (!process.waitFor(2, TimeUnit.SECONDS) && process.isAlive()) {
                    process.destroy();
                    if (!process.waitFor(2, TimeUnit.SECONDS) && process.isAlive()) {
                        process.destroyForcibly();
                        process.waitFor(2, TimeUnit.SECONDS);
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        cameraStreamLogThread = null;
    }

    private void runPostProcessingPipeline() {
        updateProcessingMessage("Validating real-time timeline...");

        Thread pipelineThread = new Thread(() -> {
            try {
                Path sessionDir = Path.of(currentSessionPath);
                ensureFileExists(sessionDir.resolve("timeline.json"), "Timeline was not generated during recording");

                updateProcessingMessage("Extracting clean audio for harmony blending...");
                String extractedWav = new FfmpegUtils().extractWav(currentSessionPath);
                if (extractedWav == null) {
                    throw new IOException("Audio extraction failed: output.wav was not created.");
                }
                ensureFileExists(Path.of(extractedWav), "Extracted wav file missing");

                updateProcessingMessage("Generating harmonized audio for the new 1 / 2m / 3m / 4 gesture map...");
                new PythonRunner().runHarmonizeAudio(currentSessionPath);
                Path harmonizedAudio = resolveHarmonizedAudio(sessionDir);
                ensureFileExists(harmonizedAudio, "Harmonized audio was not generated");

                updateProcessingMessage("Merging the captured gesture-feedback video with harmonized audio...");
                Path outputVideo = muxFinalVideo(sessionDir);
                harmonizedVideoPath = outputVideo;

                Platform.runLater(() -> {
                    isProcessing = false;
                    hideProcessingOverlay();
                    showVideoPreview(outputVideo);
                    saveVideoButton.setDisable(false);
                    startRecording.setDisable(false);
                    stopRecording.setDisable(true);
                    cancelRecording.setDisable(true);
                    status.setText("Processing complete. Review the harmonized video, then save it if you want.");
                });
            } catch (Exception e) {
                e.printStackTrace();
                Platform.runLater(() -> {
                    isProcessing = false;
                    hideProcessingOverlay();
                    startRecording.setDisable(false);
                    stopRecording.setDisable(true);
                    cancelRecording.setDisable(true);
                    status.setText("Background processing failed: " + e.getMessage());
                });
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
        Path inputVideo = resolvePreviewVideo(sessionDir);
        Path harmonizedAudio = resolveHarmonizedAudio(sessionDir);
        Path finalVideo = sessionDir.resolve("harmonized_video.mp4");

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
            throw new IOException("Failed to build the harmonized video preview. copyExit=" + copyResult.exitCode
                    + ", transcodeExit=" + transcodeResult.exitCode
                    + ", copyLogs=" + copyTail
                    + ", transcodeLogs=" + transcodeTail);
        }

        return finalVideo;
    }

    private Path resolvePreviewVideo(Path sessionDir) throws IOException {
        List<Path> candidates = List.of(
                sessionDir.resolve("preview_capture.mp4"),
                sessionDir.resolve("video.mp4")
        );

        for (Path candidate : candidates) {
            if (Files.exists(candidate) && Files.size(candidate) > 0) {
                return candidate;
            }
        }

        throw new IOException("No captured preview video was found. Expected one of: " + candidates);
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

        placeholderPane.setVisible(false);
        placeholderPane.setManaged(false);
        outputMediaView.setVisible(true);
        outputMediaView.setManaged(true);

        Media media = new Media(videoPath.toUri().toString());
        previewMediaPlayer = new MediaPlayer(media);
        previewMediaPlayer.setAutoPlay(true);
        previewMediaPlayer.setOnPlaying(() -> playPauseButton.setText("Pause"));
        previewMediaPlayer.setOnPaused(() -> playPauseButton.setText("Play"));
        previewMediaPlayer.setOnEndOfMedia(() -> playPauseButton.setText("Play"));
        outputMediaView.setMediaPlayer(previewMediaPlayer);

        previewActions.setVisible(true);
        previewActions.setManaged(true);
        playPauseButton.setDisable(false);
        replayButton.setDisable(false);
    }

    private void showPlaceholderImage() {
        stopPreviewPlayer();
        outputMediaView.setVisible(false);
        outputMediaView.setManaged(false);
        placeholderPane.setVisible(true);
        placeholderPane.setManaged(true);
        previewActions.setVisible(false);
        previewActions.setManaged(false);
    }

    private void resetPreviewForNewCapture() {
        harmonizedVideoPath = null;
        saveVideoButton.setDisable(true);
        playPauseButton.setDisable(true);
        replayButton.setDisable(true);
        showPlaceholderImage();
    }

    private void stopPreviewPlayer() {
        if (previewMediaPlayer != null) {
            previewMediaPlayer.stop();
            previewMediaPlayer.dispose();
            previewMediaPlayer = null;
        }
        outputMediaView.setMediaPlayer(null);
        playPauseButton.setText("Pause");
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

    private void deleteCurrentSessionQuietly() {
        if (currentSessionPath == null || currentSessionPath.isBlank()) {
            currentSessionPath = null;
            return;
        }

        Path sessionDir = Path.of(currentSessionPath);
        try (Stream<Path> walk = Files.walk(sessionDir)) {
            walk.sorted((a, b) -> b.compareTo(a)).forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException ignored) {
                }
            });
        } catch (IOException ignored) {
        }
        currentSessionPath = null;
    }

    private void resetToIdleState(String statusMessage) {
        sessionLabel.setText(GESTURE_GUIDE + " Recording captures the gesture-feedback window output.");
        resetPreviewForNewCapture();
        hideProcessingOverlay();
        status.setText(statusMessage);
    }

    public void shutdown() {
        isRecording = false;
        isProcessing = false;
        if (ffmpegProcess != null && ffmpegProcess.isAlive()) {
            ffmpegProcess.destroyForcibly();
        }
        stopLiveFeedbackStream();
        stopPreviewPlayer();
    }
}
