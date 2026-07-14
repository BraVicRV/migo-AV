// static/js/wake_word.js
// Detector de "Hey Migo" - Escucha activa continua
// V2: Single-Instance Architecture (sin conflictos con startMic)

class WakeWordDetector {
    constructor(options = {}) {
        this.wakePhrases = options.phrases || ['hey migo', 'hamigo', 'migo', 'aura', 'ola migo', 'ey migo', 'hey amigo'];
        this.onWakeWord = options.onWakeWord || (() => {});
        this.onInterimResult = options.onInterimResult || (() => {});
        this.onError = options.onError || (() => {});
        this.isListening = false;
        this.recognition = null;
        this.confidenceThreshold = options.confidenceThreshold || 0.4;
        this.lastTranscript = '';
        this.isSpeaking = false;
        this.wakeDetected = false;
        this.silenceTimer = null;
        this.commandBuffer = '';
        
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            console.warn('⚠️ Web Speech API no disponible');
            return;
        }
        
        console.log('🎤 WakeWordDetector inicializado');
    }
    
    _createRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        
        if (this.recognition) {
            try {
                this.recognition.onend = null;
                this.recognition.onerror = null;
                this.recognition.onresult = null;
                this.recognition.onstart = null;
                this.recognition.stop();
            } catch (e) {}
            this.recognition = null;
        }
        
        this.recognition = new SpeechRecognition();
        this.recognition.lang = 'es-ES';
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.maxAlternatives = 3;
        
        this._bindEvents();
    }
    
    _bindEvents() {
        this.recognition.onstart = () => {
            console.log('🎤 Escucha activa iniciada...');
            this.isListening = true;
        };
        
        this.recognition.onresult = (event) => {
            let finalTranscript = '';
            let interimTranscript = '';
            
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const result = event.results[i];
                const transcript = result[0].transcript.toLowerCase().trim();
                
                if (result.isFinal) {
                    finalTranscript += transcript + ' ';
                } else {
                    interimTranscript += transcript + ' ';
                }
            }
            
            finalTranscript = finalTranscript.trim();
            interimTranscript = interimTranscript.trim();
            
            if (this.wakeDetected) {
                if (finalTranscript) {
                    this.commandBuffer += ' ' + finalTranscript;
                    this.commandBuffer = this.commandBuffer.trim();
                }
                
                if (interimTranscript) {
                    this.onInterimResult(interimTranscript);
                }
                
                this._resetSilenceTimer();
                return;
            }
            
            if (interimTranscript) {
                this.onInterimResult(interimTranscript);
            }
            
            if (finalTranscript) {
                this._processTranscript(finalTranscript);
            }
        };
        
        this.recognition.onerror = (event) => {
            console.warn('⚠️ Error en reconocimiento:', event.error);
            
            if (event.error === 'no-speech') {
                return;
            }
            
            if (event.error === 'aborted') {
                if (this.isListening) {
                    console.log('🔄 Reiniciando después de abort...');
                    setTimeout(() => this._safeRestart(), 800);
                }
                return;
            }
            
            if (event.error === 'audio-capture') {
                console.warn('🔇 No se detecta micrófono');
                this.onError('No se detecta micrófono');
                this.isListening = false;
                return;
            }
            
            if (event.error === 'not-allowed') {
                console.warn('🚫 Permiso de micrófono denegado');
                this.onError('Permiso de micrófono denegado');
                this.isListening = false;
                return;
            }
            
            if (event.error === 'network') {
                console.warn('🌐 Error de red');
                setTimeout(() => this._safeRestart(), 2000);
                return;
            }
            
            if (this.isListening) {
                setTimeout(() => this._safeRestart(), 1000);
            }
        };
        
        this.recognition.onend = () => {
            console.log('🔇 Reconocimiento finalizado');
            
            if (this.wakeDetected && this.commandBuffer) {
                this._processCommand();
            }
            
            if (this.isListening) {
                setTimeout(() => this._safeRestart(), 500);
            }
        };
    }
    
    _processTranscript(transcript) {
        let detected = false;
        let wakePhrase = '';
        
        for (const phrase of this.wakePhrases) {
            const regex = new RegExp(phrase, 'i');
            if (regex.test(transcript)) {
                detected = true;
                wakePhrase = phrase;
                break;
            }
        }
        
        if (detected) {
            console.log(`🔊 Wake word detectada: "${transcript}"`);
            
            const regex = new RegExp(wakePhrase, 'i');
            const command = transcript.replace(regex, '').trim();
            
            this.wakeDetected = true;
            this.commandBuffer = command;
            this.isSpeaking = true;
            
            this.onWakeWord(command || null);
            
            this._resetSilenceTimer();
            
            setTimeout(() => {
                if (this.wakeDetected) {
                    console.log('⏰ Timeout de comando, procesando...');
                    this._processCommand();
                }
            }, 8000);
            
        } else {
            this.lastTranscript = transcript;
        }
    }
    
    _resetSilenceTimer() {
        if (this.silenceTimer) {
            clearTimeout(this.silenceTimer);
            this.silenceTimer = null;
        }
        
        if (this.wakeDetected) {
            this.silenceTimer = setTimeout(() => {
                console.log('⏳ Silencio detectado, procesando comando...');
                this._processCommand();
            }, 2500);
        }
    }
    
    _processCommand() {
        if (!this.wakeDetected) return;
        
        const command = this.commandBuffer.trim();
        console.log('📤 Procesando comando final:', command || '(vacío)');
        
        this.wakeDetected = false;
        this.commandBuffer = '';
        this.isSpeaking = false;
        
        if (this.silenceTimer) {
            clearTimeout(this.silenceTimer);
            this.silenceTimer = null;
        }
        
        if (command) {
            this.onWakeWord(command);
        }
    }
    
    _safeRestart() {
        if (!this.isListening) return;
        
        try {
            this._createRecognition();
            this.recognition.start();
            console.log('🎤 Reconocimiento reiniciado');
        } catch (e) {
            console.warn('Error reiniciando:', e);
            setTimeout(() => {
                if (this.isListening) {
                    try {
                        this._createRecognition();
                        this.recognition.start();
                    } catch (e2) {
                        console.warn('Segundo intento fallido:', e2);
                    }
                }
            }, 1500);
        }
    }
    
    start() {
        if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
            console.warn('⚠️ Speech Recognition no disponible');
            return false;
        }
        
        if (this.isListening) {
            console.log('🎤 Ya está escuchando');
            return true;
        }
        
        try {
            this._createRecognition();
            this.recognition.start();
            this.isListening = true;
            console.log('🎤 Escuchando wake word... (di "Hey Migo")');
            return true;
        } catch (e) {
            console.warn('Error iniciando wake word:', e);
            return false;
        }
    }
    
    stop() {
        if (!this.recognition) return true;
        
        this.isListening = false;
        this.wakeDetected = false;
        this.commandBuffer = '';
        
        if (this.silenceTimer) {
            clearTimeout(this.silenceTimer);
            this.silenceTimer = null;
        }
        
        try {
            this.recognition.stop();
            console.log('🔇 Wake word detenido');
            return true;
        } catch (e) {
            console.warn('Error deteniendo:', e);
            return false;
        }
    }
    
    toggle() {
        if (this.isListening) {
            return this.stop();
        } else {
            return this.start();
        }
    }
    
    isActive() {
        return this.isListening;
    }
}

if (typeof window !== 'undefined') {
    window.WakeWordDetector = WakeWordDetector;
}