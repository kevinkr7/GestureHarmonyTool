package com.harmony.gestureharmonytoolui;

import javafx.application.Application;
import javafx.fxml.FXMLLoader;
import javafx.scene.Scene;
import javafx.stage.Stage;

import java.io.File;
import java.io.IOException;

public class HarmonyApplication extends Application {
    @Override
    public void start(Stage stage) throws IOException {
        FXMLLoader fxmlLoader = new FXMLLoader(HarmonyApplication.class.getResource("hello-view.fxml"));
        Scene scene = new Scene(fxmlLoader.load(), 980, 780);
        scene.getStylesheets().add(HarmonyApplication.class.getResource("styles.css").toExternalForm());
        stage.setMinWidth(900);
        stage.setMinHeight(700);
        stage.setTitle("Gesture Harmony Studio");
        HarmonyController controller = fxmlLoader.getController();

        stage.setOnCloseRequest(event -> controller.shutdown());
        stage.setScene(scene);
        stage.show();

        File file = new File(AppPaths.SESSIONS);
    }
}
