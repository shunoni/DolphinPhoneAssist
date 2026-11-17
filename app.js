/**
 * DolphinPhoneAssist - PWA Client
 * Wiimote Controller for Dolphin Emulator
 */

(() => {
  // --- State Configuration ---
  const state = {
    connected: false,
    pairedHost: null,
    transport: null, // 'mqtt' or 'ws'
    publicIpHash: null,
    manualHostIp: localStorage.getItem('dpa_host_ip') || '',
    roomPin: localStorage.getItem('dpa_pin') || '',
    showBTrigger: localStorage.getItem('dpa_show_b') !== 'false',
    enableHaptics: localStorage.getItem('dpa_haptics') !== 'false',
    
    // Sensor values
    orientation: { alpha: 0, beta: 0, gamma: 0 },
    rotationRate: { alpha: 0, beta: 0, gamma: 0 },
    acceleration: { x: 0, y: 0, z: 1.0 },
    
    // Recenter baselines
    baseline: { alpha: 0, beta: 0, gamma: 0 },
    
    // Virtual IR cursor (-1.0 to +1.0)
    pointer: { x: 0.0, y: 0.0 },
    
    // Buttons state
    buttons: {
      up: 0,
      down: 0,
      left: 0,
      right: 0,
      a: 0,
      b: 0,
      minus: 0,
      home: 0,
      plus: 0,
      one: 0,
      two: 0
    },
    
    packetSeq: 0
  };

  // --- DOM Elements ---
  const elements = {
    overlay: document.getElementById('permission-overlay'),
    btnActivate: document.getElementById('btn-activate'),
    modal: document.getElementById('settings-modal'),
    btnCloseSettings: document.getElementById('btn-close-settings'),
    btnSaveSettings: document.getElementById('btn-save-settings'),
    inputHostIp: document.getElementById('input-host-ip'),
    inputRoomPin: document.getElementById('input-room-pin'),
    toggleBButton: document.getElementById('toggle-b-button'),
    toggleHaptics: document.getElementById('toggle-haptics'),
    statusPill: document.getElementById('status-pill'),
    statusDot: document.getElementById('status-dot'),
    statusText: document.getElementById('status-text'),
    dolphinBtn: document.getElementById('dolphin-btn'),
    btnRecenter: document.getElementById('btn-recenter'),
    recenterToast: document.getElementById('recenter-toast'),
    bTriggerContainer: document.getElementById('b-trigger-container'),
    dpad: document.getElementById('dpad')
  };

  // --- Haptics Utility ---
  function triggerHaptic(duration = 15) {
    if (state.enableHaptics && navigator.vibrate) {
      try {
        navigator.vibrate(duration);
      } catch (e) {
        // Safe fallback
      }
    }
  }

  // --- Recenter Functionality ---
  function recenterGyro() {
    state.baseline.alpha = state.orientation.alpha;
    state.baseline.beta = state.orientation.beta;
    state.baseline.gamma = state.orientation.gamma;

    // Zero out pointer
    state.pointer.x = 0;
    state.pointer.y = 0;

    triggerHaptic(30);

    // Show visual feedback
    if (elements.recenterToast) {
      elements.recenterToast.classList.remove('hidden');
      setTimeout(() => {
        elements.recenterToast.classList.add('hidden');
      }, 1500);
    }

    // Inform host
    sendImmediatePacket({
      type: 'event',
      event: 'recenter',
      baseline: state.baseline
    });
  }

  // --- Button Touch / Pointer Handlers ---
  function setupButtons() {
    const interactiveButtons = document.querySelectorAll('[data-key]');
    
    interactiveButtons.forEach(btn => {
      const key = btn.getAttribute('data-key');
      
      const onDown = (e) => {
        e.preventDefault();
        if (state.buttons[key] !== 1) {
          state.buttons[key] = 1;
          btn.classList.add('active');
          triggerHaptic(18);
          sendImmediatePacket({
            type: 'button',
            key: key,
            state: 1
          });
        }
      };

      const onUp = (e) => {
        e.preventDefault();
        if (state.buttons[key] !== 0) {
          state.buttons[key] = 0;
          btn.classList.remove('active');
          sendImmediatePacket({
            type: 'button',
            key: key,
            state: 0
          });
        }
      };

      btn.addEventListener('pointerdown', onDown);
      btn.addEventListener('pointerup', onUp);
      btn.addEventListener('pointercancel', onUp);
      btn.addEventListener('pointerleave', onUp);

      btn.addEventListener('touchstart', onDown, { passive: false });
      btn.addEventListener('touchend', onUp, { passive: false });
      btn.addEventListener('touchcancel', onUp, { passive: false });
    });

    // Recenter button click
    elements.btnRecenter.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      elements.btnRecenter.classList.add('active');
      recenterGyro();
    });
    elements.btnRecenter.addEventListener('pointerup', (e) => {
      e.preventDefault();
      elements.btnRecenter.classList.remove('active');
    });
    elements.btnRecenter.addEventListener('pointercancel', (e) => {
      e.preventDefault();
      elements.btnRecenter.classList.remove('active');
    });

    // D-Pad sliding support (multi-directional touch tracking)
    elements.dpad.addEventListener('touchmove', (e) => {
      e.preventDefault();
      const touch = e.touches[0];
      if (!touch) return;
      const target = document.elementFromPoint(touch.clientX, touch.clientY);
      const activeKey = target && target.closest('[data-key]') ? target.closest('[data-key]').getAttribute('data-key') : null;

      ['up', 'down', 'left', 'right'].forEach(dir => {
        const btn = document.getElementById(`btn-dpad-${dir}`);
        if (dir === activeKey) {
          if (state.buttons[dir] !== 1) {
            state.buttons[dir] = 1;
            btn?.classList.add('active');
            triggerHaptic(12);
            sendImmediatePacket({ type: 'button', key: dir, state: 1 });
          }
        } else {
          if (state.buttons[dir] !== 0) {
            state.buttons[dir] = 0;
            btn?.classList.remove('active');
            sendImmediatePacket({ type: 'button', key: dir, state: 0 });
          }
        }
      });
    }, { passive: false });
  }

  // --- Sensor Listeners & Normalization ---
  function setupSensors() {
    window.addEventListener('deviceorientation', (e) => {
      if (e.alpha !== null) state.orientation.alpha = e.alpha;
      if (e.beta !== null) state.orientation.beta = e.beta;
      if (e.gamma !== null) state.orientation.gamma = e.gamma;

      // Calculate relative delta for IR cursor simulation
      let relBeta = state.orientation.beta - state.baseline.beta;   // Pitch (up/down)
      let relGamma = state.orientation.gamma - state.baseline.gamma; // Roll/Yaw (left/right)

      // Clamp IR pointing coordinates to [-1.0, 1.0]
      // Sensitivity: roughly +/- 25 degrees tilt covers the full screen
      state.pointer.x = Math.max(-1.0, Math.min(1.0, relGamma / 25.0));
      state.pointer.y = Math.max(-1.0, Math.min(1.0, -relBeta / 25.0));
    });

    window.addEventListener('devicemotion', (e) => {
      if (e.accelerationIncludingGravity) {
        // Accelerometer in G's (1g = 9.80665 m/s^2)
        const g = 9.80665;
        state.acceleration.x = (e.accelerationIncludingGravity.x || 0) / g;
        state.acceleration.y = (e.accelerationIncludingGravity.y || 0) / g;
        state.acceleration.z = (e.accelerationIncludingGravity.z || g) / g;
      }

      if (e.rotationRate) {
        // Gyro in degrees/sec
        state.rotationRate.alpha = e.rotationRate.alpha || 0; // Yaw
        state.rotationRate.beta = e.rotationRate.beta || 0;   // Pitch
        state.rotationRate.gamma = e.rotationRate.gamma || 0; // Roll
      }
    });
  }

  // --- Request iOS Sensor Permissions ---
  async function requestPermissions() {
    let granted = true;

    if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
      try {
        const res = await DeviceOrientationEvent.requestPermission();
        if (res !== 'granted') granted = false;
      } catch (err) {
        console.warn('DeviceOrientationEvent permission error:', err);
      }
    }

    if (typeof DeviceMotionEvent !== 'undefined' && typeof DeviceMotionEvent.requestPermission === 'function') {
      try {
        const res = await DeviceMotionEvent.requestPermission();
        if (res !== 'granted') granted = false;
      } catch (err) {
        console.warn('DeviceMotionEvent permission error:', err);
      }
    }

    if (granted) {
      setupSensors();
      elements.overlay.classList.add('hidden');
      initNetworking();
      startStreamingLoop();
    } else {
      alert('Motion sensor permission is needed to use Gyro / Wiimote motion controls.');
    }
  }

  // --- Networking & Auto-Discovery ---
  let mqttClient = null;
  let directWs = null;
  let activeTopic = null;

  async function computeNetworkHash() {
    try {
      const res = await fetch('https://api.ipify.org?format=json');
      const data = await res.json();
      const ip = data.ip || 'local';
      // Simple hash of public IP to group devices on same WiFi
      let hash = 0;
      for (let i = 0; i < ip.length; i++) {
        hash = ((hash << 5) - hash) + ip.charCodeAt(i);
        hash |= 0;
      }
      return 'dpa_' + Math.abs(hash).toString(16);
    } catch (e) {
      console.warn('Could not determine public IP, using fallback channel:', e);
      return 'dpa_local_default';
    }
  }

  async function initNetworking() {
    updateStatus('searching', 'Searching for Host...');

    // 1. Direct WebSocket fallback if user specified Host IP
    if (state.manualHostIp) {
      connectDirectWs(state.manualHostIp);
      return;
    }

    // 2. Public MQTT Signaling & Pairing (HiveMQ / EMQX WSS Broker)
    state.publicIpHash = await computeNetworkHash();
    
    // Pairing topic: room PIN if provided, otherwise network IP hash
    const room = state.roomPin ? `pin_${state.roomPin}` : state.publicIpHash;
    activeTopic = `dolphinphone/room/${room}`;

    console.log(`[DPA] Subscribing to pairing room: ${activeTopic}`);

    const brokerUrl = 'wss://broker.emqx.io:8084/mqtt';
    const clientId = 'wiimote_' + Math.random().toString(16).substring(2, 8);

    try {
      mqttClient = mqtt.connect(brokerUrl, {
        clientId: clientId,
        clean: true,
        connectTimeout: 5000,
        keepalive: 30
      });

      mqttClient.on('connect', () => {
        console.log('[DPA] Connected to signaling broker');
        mqttClient.subscribe(`${activeTopic}/#`);

        // Announce phone presence
        mqttClient.publish(`${activeTopic}/client`, JSON.stringify({
          event: 'client_hello',
          device: 'iPhone Wiimote',
          time: Date.now()
        }));

        updateStatus('searching', 'Looking for Host...');
      });

      mqttClient.on('message', (topic, message) => {
        try {
          const data = JSON.parse(message.toString());
          
          if (data.event === 'host_announce' || data.event === 'host_ack') {
            state.connected = true;
            state.transport = 'mqtt';
            state.pairedHost = data.host_name || 'PiOS Host';
            updateStatus('connected', `Connected: ${state.pairedHost}`);
            triggerHaptic(40);
          }
        } catch (e) {
          console.error('[DPA] Error parsing packet:', e);
        }
      });

      mqttClient.on('error', (err) => {
        console.warn('[DPA] MQTT Error:', err);
        updateStatus('error', 'Signaling Error');
      });

      mqttClient.on('close', () => {
        if (state.connected) {
          state.connected = false;
          updateStatus('searching', 'Reconnecting...');
        }
      });
    } catch (err) {
      console.error('[DPA] MQTT connect exception:', err);
    }
  }

  function connectDirectWs(ip) {
    updateStatus('searching', `Connecting to ${ip}...`);
    try {
      const port = ip.includes(':') ? '' : ':8000';
      const wsUrl = `ws://${ip}${port}/ws`;
      directWs = new WebSocket(wsUrl);

      directWs.onopen = () => {
        state.connected = true;
        state.transport = 'ws';
        updateStatus('connected', `Connected: ${ip}`);
        triggerHaptic(40);
      };

      directWs.onclose = () => {
        state.connected = false;
        updateStatus('error', 'Disconnected');
      };

      directWs.onerror = () => {
        updateStatus('error', 'Connection Failed');
      };
    } catch (e) {
      console.error('Direct WS error:', e);
      updateStatus('error', 'Error');
    }
  }

  function updateStatus(dotClass, text) {
    elements.statusDot.className = `status-dot ${dotClass}`;
    elements.statusText.textContent = text;
  }

  // --- Packet Dispatch ---
  function sendImmediatePacket(payload) {
    if (!state.connected) return;

    const data = JSON.stringify(payload);
    if (state.transport === 'ws' && directWs && directWs.readyState === WebSocket.OPEN) {
      directWs.send(data);
    } else if (state.transport === 'mqtt' && mqttClient && mqttClient.connected && activeTopic) {
      mqttClient.publish(`${activeTopic}/input`, data, { qos: 0 });
    }
  }

  // --- 60Hz Streaming Loop for Continuous Motion ---
  function startStreamingLoop() {
    const TARGET_FPS = 60;
    const intervalMs = 1000 / TARGET_FPS;

    setInterval(() => {
      if (!state.connected) return;

      state.packetSeq = (state.packetSeq + 1) & 0xFFFFFFFF;

      // Relative motion angles
      const relBeta = state.orientation.beta - state.baseline.beta;
      const relGamma = state.orientation.gamma - state.baseline.gamma;
      const relAlpha = state.orientation.alpha - state.baseline.alpha;

      const motionPacket = {
        type: 'state',
        seq: state.packetSeq,
        buttons: { ...state.buttons },
        motion: {
          accel_x: parseFloat(state.acceleration.x.toFixed(4)),
          accel_y: parseFloat(state.acceleration.y.toFixed(4)),
          accel_z: parseFloat(state.acceleration.z.toFixed(4)),
          gyro_pitch: parseFloat(state.rotationRate.beta.toFixed(2)),
          gyro_yaw: parseFloat(state.rotationRate.alpha.toFixed(2)),
          gyro_roll: parseFloat(state.rotationRate.gamma.toFixed(2)),
          rel_pitch: parseFloat(relBeta.toFixed(2)),
          rel_roll: parseFloat(relGamma.toFixed(2)),
          rel_yaw: parseFloat(relAlpha.toFixed(2)),
          pointer_x: parseFloat(state.pointer.x.toFixed(3)),
          pointer_y: parseFloat(state.pointer.y.toFixed(3))
        }
      };

      sendImmediatePacket(motionPacket);
    }, intervalMs);
  }

  // --- Settings UI Handlers ---
  function setupSettings() {
    // Populate stored values
    elements.inputHostIp.value = state.manualHostIp;
    elements.inputRoomPin.value = state.roomPin;
    elements.toggleBButton.checked = state.showBTrigger;
    elements.toggleHaptics.checked = state.enableHaptics;

    applyBTriggerVisibility();

    // Open settings on clicking status pill or Dolphin logo
    elements.statusPill.addEventListener('click', () => {
      elements.modal.classList.remove('hidden');
    });
    elements.dolphinBtn.addEventListener('click', () => {
      elements.modal.classList.remove('hidden');
    });

    elements.btnCloseSettings.addEventListener('click', () => {
      elements.modal.classList.add('hidden');
    });

    elements.btnSaveSettings.addEventListener('click', () => {
      state.manualHostIp = elements.inputHostIp.value.trim();
      state.roomPin = elements.inputRoomPin.value.trim();
      state.showBTrigger = elements.toggleBButton.checked;
      state.enableHaptics = elements.toggleHaptics.checked;

      localStorage.setItem('dpa_host_ip', state.manualHostIp);
      localStorage.setItem('dpa_pin', state.roomPin);
      localStorage.setItem('dpa_show_b', state.showBTrigger);
      localStorage.setItem('dpa_haptics', state.enableHaptics);

      applyBTriggerVisibility();
      elements.modal.classList.add('hidden');

      // Reconnect
      if (mqttClient) mqttClient.end();
      if (directWs) directWs.close();
      initNetworking();
    });
  }

  function applyBTriggerVisibility() {
    if (elements.bTriggerContainer) {
      elements.bTriggerContainer.style.display = state.showBTrigger ? 'flex' : 'none';
    }
  }

  // --- Initialization ---
  function init() {
    setupButtons();
    setupSettings();

    elements.btnActivate.addEventListener('click', () => {
      requestPermissions();
    });

    // Check if permission API doesn't exist (non-iOS or modern desktop browser)
    if (typeof DeviceOrientationEvent === 'undefined' || typeof DeviceOrientationEvent.requestPermission !== 'function') {
      elements.overlay.classList.add('hidden');
      setupSensors();
      initNetworking();
      startStreamingLoop();
    }
  }

  // Launch on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
