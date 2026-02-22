package com.harmony.gestureharmonytoolui;

public class SessionConfig {
    public final String key;
    public final String scale;
    public final int voices;
    public final double mix;

    public SessionConfig(String key, String scale, int voices, double mix) {
        this.key = key;
        this.scale = scale;
        this.voices = voices;
        this.mix = mix;
    }
}
