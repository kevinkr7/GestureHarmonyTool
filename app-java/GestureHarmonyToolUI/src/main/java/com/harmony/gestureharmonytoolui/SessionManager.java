package com.harmony.gestureharmonytoolui;

import java.io.File;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public class SessionManager {
    public static String createNewSession() {
        String base = AppPaths.SESSIONS;
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss");
        String id = LocalDateTime.now().format(formatter);
        String folderName = base + "/session_" + id;

        File file = new File(folderName);
        file.mkdirs();
        return file.getAbsolutePath();
    }
}
