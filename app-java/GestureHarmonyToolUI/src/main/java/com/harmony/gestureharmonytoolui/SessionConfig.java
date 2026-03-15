package com.harmony.gestureharmonytoolui;

public class SessionConfig {
    public final int voices;
    public final double mix;
    public final double reverbIntensity;

    public SessionConfig(int voices, double mix, double reverbIntensity) {
        this.voices = voices;
        this.mix = mix;
        this.reverbIntensity = reverbIntensity;
    }
}
