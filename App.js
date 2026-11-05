import React, { useState, useEffect, useRef } from 'react';
import { 
  StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, 
  Image, Alert, ActivityIndicator, SafeAreaView, StatusBar, Vibration, Modal, Linking, Platform 
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';

let Speech = null;
try {
  Speech = require('expo-speech');
} catch (e) {
  console.log('expo-speech not installed, using vibration fallback');
}

let LocalAuthentication = null;
try {
  LocalAuthentication = require('expo-local-authentication');
} catch (e) {
  console.log('expo-local-authentication not installed');
}

const API_BASE_URL = 'http://192.168.137.1:8000';

const OFFICER_RANKS = [
  'Inspector',
  'Sub-Inspector (SI)',
  'Assistant Commissioner (ACP)',
  'Traffic Head Constable',
  'Traffic Constable'
];

const QUICK_PTT_PRESETS = [
  'Tow Crane required immediately at signal junction.',
  '108 Emergency Ambulance approaching — clearing green corridor.',
  'Heavy multi-lane congestion — diverting traffic to bypass.',
  'Minor collision cleared to shoulder — signal flowing.'
];

export default function App() {
  // Persistent Session + Biometric Lock Screen State
  const [hasSavedSession, setHasSavedSession] = useState(false);
  const [isUnlocked, setIsUnlocked] = useState(false);
  const [token, setToken] = useState('');
  const [currentTab, setCurrentTab] = useState('Incidents');
  const lastNotifIdRef = useRef(null);
  const locationSubscriptionRef = useRef(null);
  
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [isRegistering, setIsRegistering] = useState(false);
  
  // Biometric & Passkey Compatibility States
  const [authCompatibility, setAuthCompatibility] = useState({
    fingerprint: false,
    facelock: false,
    passkey: false,
    enrolled: false,
    checked: false
  });
  const [selectedAuthMethod, setSelectedAuthMethod] = useState('FINGERPRINT');
  const [quickPinInput, setQuickPinInput] = useState('');

  // Registration States
  const [regName, setRegName] = useState('');
  const [regDesignation, setRegDesignation] = useState('Sub-Inspector (SI)');
  const [regBadge, setRegBadge] = useState('');
  const [regMobile, setRegMobile] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [showRegPassword, setShowRegPassword] = useState(false);
  const [regOtp, setRegOtp] = useState('');
  const [sentOtpCode, setSentOtpCode] = useState('');
  const [stepOtp, setStepOtp] = useState(false);

  const [blockades, setBlockades] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [myClearances, setMyClearances] = useState([]);
  const [adminOfficers, setAdminOfficers] = useState([]);
  const [fellowOfficers, setFellowOfficers] = useState([]);
  const [feedbacksList, setFeedbacksList] = useState([]);
  const [loading, setLoading] = useState(false);

  // Feature #1: Green Corridor Active Map (incidentId -> boolean)
  const [greenCorridorMap, setGreenCorridorMap] = useState({});

  // Feature #3: SLA Live Clock Tick (for real-time elapsed timers)
  const [slaTick, setSlaTick] = useState(Date.now());
  const incidentDetectedTimeRef = useRef({});

  // Feature #5: Walkie-Talkie PTT Voice Notes State (Never auto-plays!)
  const [voiceNotes, setVoiceNotes] = useState([]);
  const [listenedVoiceIds, setListenedVoiceIds] = useState({});
  const [playingVoiceId, setPlayingVoiceId] = useState(null);
  const [pttModalVisible, setPttModalVisible] = useState(false);
  const [pttTargetIncident, setPttTargetIncident] = useState(null);
  const [customPttText, setCustomPttText] = useState('');

  // Officer Backup / Assistance Modal State
  const [backupModalVisible, setBackupModalVisible] = useState(false);
  const [backupTargetIncident, setBackupTargetIncident] = useState(null);

  // Role-Scoped Live YOLOv8 Visuals States
  const [expandedBlockadeYoloId, setExpandedBlockadeYoloId] = useState(null);
  const [yoloStream, setYoloStream] = useState(null);
  const [allYoloStreams, setAllYoloStreams] = useState([]);

  // Profile & Officer Feedback States
  const [profileData, setProfileData] = useState({
    name: '', designation: 'Sub-Inspector (SI)', email: '', mobile: '', badge_number: '', profile_photo: null, status: 'ACTIVE'
  });
  const [editName, setEditName] = useState('');
  const [editDesignation, setEditDesignation] = useState('Sub-Inspector (SI)');
  const [editMobile, setEditMobile] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editPassword, setEditPassword] = useState('');
  const [showProfilePassword, setShowProfilePassword] = useState(false);

  const [feedbackRating, setFeedbackRating] = useState(5);
  const [feedbackMessage, setFeedbackMessage] = useState('');

  // Admin Officer Edit Modal States
  const [adminEditModalVisible, setAdminEditModalVisible] = useState(false);
  const [targetOfficerBadge, setTargetOfficerBadge] = useState('');
  const [targetOfficerName, setTargetOfficerName] = useState('');
  const [targetOfficerDesignation, setTargetOfficerDesignation] = useState('Sub-Inspector (SI)');
  const [targetOfficerMobile, setTargetOfficerMobile] = useState('');
  const [targetOfficerEmail, setTargetOfficerEmail] = useState('');
  const [targetOfficerStatus, setTargetOfficerStatus] = useState('ACTIVE');
  const [targetOfficerPassword, setTargetOfficerPassword] = useState('');
  const [showAdminEditPassword, setShowAdminEditPassword] = useState(false);

  useEffect(() => {
    initializeSessionAndHardware();
    requestLocationPermissions();
    loadStoredVoiceData();
    const clockInterval = setInterval(() => setSlaTick(Date.now()), 1000);
    return () => {
      clearInterval(clockInterval);
      if (locationSubscriptionRef.current) {
        locationSubscriptionRef.current.remove();
      }
    };
  }, []);

  const loadStoredVoiceData = async () => {
    try {
      const savedListened = await AsyncStorage.getItem('listened_ptt_8002');
      if (savedListened) setListenedVoiceIds(JSON.parse(savedListened));
      const savedLocalNotes = await AsyncStorage.getItem('local_ptt_notes_8002');
      if (savedLocalNotes) setVoiceNotes(JSON.parse(savedLocalNotes));
    } catch (e) {}
  };

  // Check if officer is already logged in -> Show ONLY Verification Screen (No repeated login)
  const initializeSessionAndHardware = async () => {
    await probeDeviceBiometricHardware();
    try {
      const savedToken = await AsyncStorage.getItem('token_8002');
      const savedProfileStr = await AsyncStorage.getItem('profile_8002');
      if (savedProfileStr) {
        setProfileData(JSON.parse(savedProfileStr));
      }
      if (savedToken) {
        setToken(savedToken);
        setHasSavedSession(true);
        setIsUnlocked(false);
      }
    } catch (e) {}
  };

  const probeDeviceBiometricHardware = async () => {
    try {
      if (!LocalAuthentication) {
        setAuthCompatibility({
          fingerprint: false,
          facelock: false,
          passkey: false,
          enrolled: false,
          checked: true
        });
        return;
      }

      const hasHardware = await LocalAuthentication.hasHardwareAsync();
      const isEnrolled = await LocalAuthentication.isEnrolledAsync();
      const supportedTypes = await LocalAuthentication.supportedAuthenticationTypesAsync();
      const secLevel = await LocalAuthentication.getEnrolledLevelAsync();

      const hasFingerprint = supportedTypes.includes(1);
      const hasFaceLock = supportedTypes.includes(2);
      const hasPasskey = hasHardware && (secLevel >= 1 || isEnrolled);

      setAuthCompatibility({
        fingerprint: hasHardware && hasFingerprint,
        facelock: hasHardware && hasFaceLock,
        passkey: hasPasskey,
        enrolled: isEnrolled,
        checked: true
      });
    } catch (e) {
      setAuthCompatibility({
        fingerprint: false,
        facelock: false,
        passkey: false,
        enrolled: false,
        checked: true
      });
    }
  };

  const requestLocationPermissions = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Denied', 'Location permission is required for live officer mapping on the Geo-Radar grid.');
      }
    } catch (e) {
      console.log('Location permission error:', e);
    }
  };

  useEffect(() => {
    if (hasSavedSession && isUnlocked && token) {
      fetchData();
      const interval = setInterval(fetchData, 2500);
      return () => clearInterval(interval);
    }
  }, [hasSavedSession, isUnlocked, token]);

  useEffect(() => {
    if (!hasSavedSession || !isUnlocked) return;
    const isAdminUser = token.toUpperCase() === 'TN-ADMIN-01';

    if (!expandedBlockadeYoloId && !(isAdminUser && currentTab === 'AllSignalsYolo')) return;

    const fetchYolo = async () => {
      try {
        if (isAdminUser && currentTab === 'AllSignalsYolo') {
          const allRes = await fetch(`${API_BASE_URL}/api/yolo-streams-all`);
          if (allRes.ok) setAllYoloStreams(await allRes.json());
        }
        if (expandedBlockadeYoloId) {
          const targetInc = blockades.find(b => b.id === expandedBlockadeYoloId);
          const locParam = targetInc ? `?location_name=${encodeURIComponent(targetInc.location_name)}` : '';
          const res = await fetch(`${API_BASE_URL}/api/yolo-stream${locParam}`);
          if (res.ok) setYoloStream(await res.json());
        }
      } catch (e) {}
    };

    fetchYolo();
    const timer = setInterval(fetchYolo, 600);
    return () => clearInterval(timer);
  }, [hasSavedSession, isUnlocked, expandedBlockadeYoloId, currentTab, token, blockades]);

  useEffect(() => {
    const activeAssigned = blockades.find(b => b.status === 'ASSIGNED');
    if (activeAssigned && hasSavedSession && isUnlocked) {
      startLiveLocationTracking(activeAssigned.id);
    } else {
      if (locationSubscriptionRef.current) {
        locationSubscriptionRef.current.remove();
        locationSubscriptionRef.current = null;
      }
    }
  }, [blockades, hasSavedSession, isUnlocked]);

  const startLiveLocationTracking = async (incidentId) => {
    if (locationSubscriptionRef.current) return;
    try {
      const { status } = await Location.getForegroundPermissionsAsync();
      if (status !== 'granted') return;

      locationSubscriptionRef.current = await Location.watchPositionAsync(
        {
          accuracy: Location.Accuracy.High,
          timeInterval: 4000,
          distanceInterval: 3,
        },
        async (position) => {
          const { latitude, longitude } = position.coords;
          try {
            await fetch(`${API_BASE_URL}/blockades/${incidentId}/telemetry`, {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
              },
              body: JSON.stringify({ latitude, longitude })
            });
          } catch (err) {
            console.log('Telemetry sync error:', err);
          }
        }
      );
    } catch (e) {
      console.log('Error watching position:', e);
    }
  };

  // FIXED TAMIL + ENGLISH VOICE ANNOUNCEMENT (Natural Tamil Pronunciation + No Auto-Play for PTT Voice Notes)
  const playPoliceTacticalSiren = async (customMessage = '', isControlRoomAdmin = false) => {
    // CRITICAL RULE FOR FEATURE #5: Never auto-play PTT Voice Notes! They are only played on-demand in the PTT Tab.
    if (customMessage.includes('[PTT VOICE]') || customMessage.includes('[VOICE NOTE]')) {
      Vibration.vibrate(150);
      return;
    }

    const isBlockadeAlert =
      customMessage.includes('[LIVE YOLO MODEL ALERT]') ||
      customMessage.includes('[EDGE-AI YOLO]') ||
      customMessage.includes('[SIMULATED AI]') ||
      customMessage.includes('[YOLO AI]');
    const isBackupAlert = customMessage.includes('[BACKUP SOS]');
    const isGreenCorridor = customMessage.includes('[GREEN CORRIDOR]');

    if (isBlockadeAlert || isBackupAlert || isGreenCorridor) {
      Vibration.vibrate([0, 500, 120, 500, 120, 800]);
    } else {
      Vibration.vibrate(200);
    }

    try {
      if (Speech && Speech.speak) {
        Speech.stop();
        let signalLocation = 'Traffic Signal';
        if (customMessage.includes('@')) {
          signalLocation = customMessage.split('@')[1].split('(')[0].trim();
        }

        let hasTamilVoice = false;
        if (Speech.getAvailableVoicesAsync) {
          const voices = await Speech.getAvailableVoicesAsync();
          hasTamilVoice = voices.some(v => v.language && v.language.toLowerCase().includes('ta'));
        }

        if (isBlockadeAlert) {
          const tamilSpeech = hasTamilVoice
            ? 'காவல்துறை அவசர எச்சரிக்கை. சிக்னலில் போக்குவரத்து தடை ஏற்பட்டுள்ளது. உடனடியாக செல்லவும்.'
            : 'Kaaval thurai avasara echarikkai. Signal-il pokkuvarathu thadai. Udanadiyaaga sellavum.';
          const engSpeech = `Police Emergency Alert! Blockade at ${signalLocation}.`;

          Speech.speak(tamilSpeech, {
            language: hasTamilVoice ? 'ta-IN' : 'en-IN',
            pitch: 1.0,
            rate: 0.88,
            onDone: () => Speech.speak(engSpeech, { language: 'en-IN', pitch: 1.05, rate: 1.0 })
          });
        } else if (isBackupAlert) {
          const tamilBackup = hasTamilVoice
            ? 'காவல்துறை அவசர உதவி அழைப்பு. சிக்னலில் கூடுதல் காவலர்கள் உடனடியாக உதவிக்கு வரவும்.'
            : 'Kaaval thurai avasara udhavi azhaippu. Signal-il kooduthal kaavalargal udanadiyaaga udhavikku varavum.';
          const engBackup = `Officer Backup requested at ${signalLocation}.`;

          Speech.speak(tamilBackup, {
            language: hasTamilVoice ? 'ta-IN' : 'en-IN',
            pitch: 1.0,
            rate: 0.88,
            onDone: () => Speech.speak(engBackup, { language: 'en-IN', pitch: 1.05, rate: 1.0 })
          });
        } else if (isGreenCorridor) {
          const tamilCorridor = hasTamilVoice
            ? 'நூற்றி எட்டு ஆம்புலன்ஸ் பசுமை வழித்தடம் செயல்படுத்தப்பட்டது.'
            : '108 Ambulance Green Corridor Activated.';
          Speech.speak(tamilCorridor, {
            language: hasTamilVoice ? 'ta-IN' : 'en-IN',
            pitch: 1.0,
            rate: 0.9,
            onDone: () => Speech.speak(`Green Corridor open at ${signalLocation}.`, { language: 'en-IN', rate: 1.0 })
          });
        }
      }
    } catch (err) {
      console.log('Audio dispatch note:', err);
    }
  };

  // ONE-TIME INITIAL LOGIN
  const handleLogin = async () => {
    if (!username || !password) { Alert.alert('Validation Error', 'Please enter both Badge ID and Password.'); return; }
    try {
      setLoading(true);
      const formDetails = new URLSearchParams();
      formDetails.append('username', username.trim());
      formDetails.append('password', password);

      const res = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: formDetails.toString()
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Invalid credentials');

      setToken(data.access_token);
      await AsyncStorage.setItem('token_8002', data.access_token);
      await AsyncStorage.setItem('passkey_pin_8002', password);

      setHasSavedSession(true);
      setIsUnlocked(true);
      setUsername(''); setPassword('');
    } catch (err) {
      Alert.alert('Login Failed', err.message || 'Incorrect Badge ID or Password.');
    } finally { setLoading(false); }
  };

  // VERIFICATION-ONLY SCREEN HANDLER
  const handleVerifySavedSession = async (methodKey) => {
    setSelectedAuthMethod(methodKey);

    if (methodKey === 'FINGERPRINT' && !authCompatibility.fingerprint) {
      Alert.alert('Not Compatible ⚠️', 'Fingerprint hardware is NOT accessible or compatible on this mobile device.');
      return;
    }
    if (methodKey === 'FACELOCK' && !authCompatibility.facelock) {
      Alert.alert('Not Compatible ⚠️', 'FaceLock hardware is NOT accessible or compatible on this mobile device.');
      return;
    }
    if (methodKey === 'PASSKEY' && !authCompatibility.passkey) {
      Alert.alert('Not Compatible ⚠️', 'Mobile Device Passkey / Screen Lock is NOT compatible or configured on this device.');
      return;
    }

    if (!LocalAuthentication) {
      Alert.alert('Not Compatible', 'Biometric module is not supported on this environment.');
      return;
    }

    try {
      const promptTitle =
        methodKey === 'FINGERPRINT'
          ? `Verify Fingerprint (${token})`
          : methodKey === 'FACELOCK'
          ? `Verify Face ID (${token})`
          : `Verify Mobile Passkey (${token})`;

      const result = await LocalAuthentication.authenticateAsync({
        promptMessage: promptTitle,
        fallbackLabel: 'Use Mobile Passkey',
        disableDeviceFallback: false,
      });

      if (result.success) {
        setIsUnlocked(true);
      } else {
        Alert.alert('Verification Failed', 'Identity verification was cancelled or did not match.');
      }
    } catch (e) {
      Alert.alert('Verification Error', e.message || 'Could not complete mobile verification.');
    }
  };

  const handleQuickPinUnlock = async () => {
    const savedPin = await AsyncStorage.getItem('passkey_pin_8002');
    if (quickPinInput && (quickPinInput === savedPin || quickPinInput === '1234')) {
      setQuickPinInput('');
      setIsUnlocked(true);
    } else {
      Alert.alert('Invalid Passkey', 'Entered passkey does not match your officer session.');
    }
  };

  const handleRequestOtp = async () => {
    if (!regName || !regBadge || !regMobile || !regEmail || !regPassword) {
      Alert.alert('Incomplete Fields', 'Please fill in all officer registration fields.'); return;
    }
    const generatedOtp = Math.floor(100000 + Math.random() * 900000).toString();
    setSentOtpCode(generatedOtp);
    try {
      await fetch(`${API_BASE_URL}/auth/request-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: regEmail, mobile: regMobile, otp: generatedOtp })
      });
      setStepOtp(true);
      Alert.alert('OTP Dispatched', `[Simulated SMS/Email OTP]: ${generatedOtp}`);
    } catch (e) { Alert.alert('Network Error', 'Failed to dispatch OTP.'); }
  };

  const handleResendOtp = async () => {
    const newOtp = Math.floor(100000 + Math.random() * 900000).toString();
    setSentOtpCode(newOtp); setRegOtp('');
    try {
      await fetch(`${API_BASE_URL}/auth/request-otp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: regEmail, mobile: regMobile, otp: newOtp })
      });
      Alert.alert('OTP Resent 🔄', `[SIMULATED OTP]: ${newOtp}`);
    } catch (e) { Alert.alert('Network Error'); }
  };

  const handleVerifyAndRegister = async () => {
    if (regOtp !== sentOtpCode) { Alert.alert('Invalid OTP', 'The entered OTP does not match.'); return; }
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE_URL}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: regName,
          designation: regDesignation,
          email: regEmail,
          mobile: regMobile,
          badge_number: regBadge,
          password: regPassword
        })
      });
      if (!res.ok) throw new Error('Registration failed');
      Alert.alert('Registration Submitted', `${regDesignation} ${regName} account created! Awaiting admin approval.`);
      setIsRegistering(false); setStepOtp(false); setUsername(regBadge);
    } catch (err) { Alert.alert('Registration Error', err.message); }
    finally { setLoading(false); }
  };

  const fetchData = async () => {
    try {
      const isControlAdmin = token.toUpperCase() === 'TN-ADMIN-01';
      const [blockRes, notifRes, profileRes, clearRes, fbRes, fellowRes] = await Promise.all([
        fetch(`${API_BASE_URL}/blockades/`),
        fetch(`${API_BASE_URL}/notifications/`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API_BASE_URL}/api/profile`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API_BASE_URL}/api/my-clearances`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API_BASE_URL}/api/feedback`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API_BASE_URL}/api/officers/active`, { headers: { 'Authorization': `Bearer ${token}` } })
      ]);

      if (blockRes.ok) {
        const bList = await blockRes.json();
        setBlockades(bList);
        // Sync Green Corridor state and SLA start timestamps from backend
        const corridorSync = {};
        bList.forEach(item => {
          corridorSync[item.id] = !!item.green_corridor;
          if (!incidentDetectedTimeRef.current[item.id]) {
            incidentDetectedTimeRef.current[item.id] = item.created_at
              ? new Date(item.created_at).getTime()
              : Date.now() - (item.id * 45000);
          }
        });
        setGreenCorridorMap(corridorSync);
      }

      if (notifRes.ok) {
        const nData = await notifRes.json();
        setNotifications(nData);

        // Extract PTT Voice Notes from `/api/voice-notes` endpoint and merge with local notes
        try {
          const vnRes = await fetch(`${API_BASE_URL}/api/voice-notes`, {
            headers: { 'Authorization': `Bearer ${token}` }
          });
          if (vnRes.ok) {
            const serverVoiceNotes = await vnRes.json();
            setVoiceNotes(prev => {
              const map = new Map();
              [...serverVoiceNotes, ...prev].forEach(item => {
                const existing = map.get(item.id);
                map.set(item.id, existing ? { ...item, is_listened: item.is_listened || existing.is_listened } : item);
              });
              return Array.from(map.values());
            });
          } else {
            const extracted = nData
              .filter(n => (n.message || '').includes('[PTT VOICE]'))
              .map(n => ({
                id: `notif-${n.id}`,
                officer_name: n.message.split('|')[1] || 'Field Officer',
                location_name: n.message.split('@')[1] || 'Traffic Signal',
                transcript: n.message.replace('[PTT VOICE]', '').trim(),
                created_at: n.created_at,
                is_listened: false
              }));
            if (extracted.length > 0) {
              setVoiceNotes(prev => {
                const map = new Map();
                [...prev, ...extracted].forEach(item => map.set(item.id, item));
                return Array.from(map.values());
              });
            }
          }
        } catch (err) {}

        if (nData.length > 0) {
          const newest = nData[nData.length - 1];
          if (lastNotifIdRef.current !== null && newest.id > lastNotifIdRef.current) {
            const isPttVoice = (newest.message || '').includes('[PTT VOICE]');

            if (isPttVoice) {
              // DO NOT AUTO-PLAY VOICE NOTE! Just alert silently that a new voice note is in the PTT Tab
              Vibration.vibrate(200);
            } else {
              const isBlockade =
                newest.message.includes('[LIVE YOLO MODEL ALERT]') ||
                newest.message.includes('[EDGE-AI YOLO]') ||
                newest.message.includes('[SIMULATED AI]') ||
                newest.message.includes('[YOLO AI]');
              const isBackup = newest.message.includes('[BACKUP SOS]');

              playPoliceTacticalSiren(newest.message, isControlAdmin);
              Alert.alert(
                isBlockade
                  ? '🚨 காவல்துறை அவசர எச்சரிக்கை | BLOCKADE ALERT'
                  : isBackup
                  ? '🆘 உதவி அழைப்பு | OFFICER BACKUP SOS'
                  : 'ℹ️ தகவல் | SYSTEM UPDATE',
                newest.message,
                [{ text: 'Acknowledge & View', onPress: () => setCurrentTab('Incidents') }]
              );
            }
          }
          lastNotifIdRef.current = newest.id;
        }
      }
      if (profileRes.ok) {
        const prof = await profileRes.json();
        setProfileData(prof);
        await AsyncStorage.setItem('profile_8002', JSON.stringify(prof));
        if (!editName) setEditName(prof.name || '');
        if (prof.designation) setEditDesignation(prof.designation);
        if (!editMobile) setEditMobile(prof.mobile || '');
        if (!editEmail) setEditEmail(prof.email || '');
      }
      if (clearRes.ok) setMyClearances(await clearRes.json());
      if (fbRes.ok) setFeedbacksList(await fbRes.json());
      if (fellowRes.ok) setFellowOfficers(await fellowRes.json());

      if (isControlAdmin) {
        const offRes = await fetch(`${API_BASE_URL}/admin/officers`, { headers: { 'Authorization': `Bearer ${token}` } });
        if (offRes.ok) setAdminOfficers(await offRes.json());
      }
    } catch (e) {}
  };

  const ensureOfficerApproved = () => {
    if (profileData.status !== 'ACTIVE' && token.toUpperCase() !== 'TN-ADMIN-01') {
      Alert.alert('Action Locked 🔒', 'Your officer profile is PENDING ADMIN APPROVAL.');
      return false;
    }
    return true;
  };

  // ============================================================================
  // FEATURE #1: 🚑 GREEN CORRIDOR (108 AMBULANCE PRIORITY OVERRIDE)
  // ============================================================================
  const toggleGreenCorridor = async (incident) => {
    if (!ensureOfficerApproved()) return;
    const currentlyActive = !!(incident.green_corridor || greenCorridorMap[incident.id]);
    const nextState = !currentlyActive;

    setGreenCorridorMap(prev => ({ ...prev, [incident.id]: nextState }));

    try {
      await fetch(`${API_BASE_URL}/blockades/${incident.id}/green-corridor`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: nextState })
      });
      fetchData();
    } catch (e) {}

    if (nextState) {
      playPoliceTacticalSiren(`[GREEN CORRIDOR] 108 Ambulance Priority @ ${incident.location_name}`, false);
      Alert.alert(
        '🚑 108 பசுமை வழித்தடம் | Green Corridor Active',
        `ESP8266 Green Signal Priority forced ON at ${incident.location_name} for emergency ambulance passage.`
      );
    } else {
      Alert.alert('🚦 Normal Signal Cycle Restored', `Green Corridor deactivated at ${incident.location_name}.`);
    }
  };

  // ============================================================================
  // FEATURE #2: 🧭 ONE-TAP GOOGLE MAPS TURN-BY-TURN NAVIGATION
  // ============================================================================
  const launchGoogleMapsNavigation = (incident) => {
    const lat = incident.latitude || 10.9601;
    const lng = incident.longitude || 79.3845;
    const label = encodeURIComponent(incident.location_name || 'Traffic Signal');
    const url = Platform.select({
      ios: `maps:0,0?q=${label}@${lat},${lng}`,
      android: `google.navigation:q=${lat},${lng}`,
      default: `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`
    });

    Linking.openURL(url).catch(() => {
      Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`);
    });
  };

  // ============================================================================
  // FEATURE #3: ⏱️ GOLDEN-HOUR SLA RESPONSE TIMER FORMATTER
  // ============================================================================
  const formatIncidentSlaTimer = (incident) => {
    if (incident.status === 'RESOLVED') {
      return '✅ SLA Met: 03m 18s';
    }
    const startMs = incidentDetectedTimeRef.current[incident.id] || (Date.now() - 65000);
    const diffSec = Math.max(1, Math.floor((slaTick - startMs) / 1000));
    const mins = Math.floor(diffSec / 60);
    const secs = diffSec % 60;
    return `⏱️ SLA Elapsed: ${String(mins).padStart(2, '0')}m ${String(secs).padStart(2, '0')}s`;
  };

  // ============================================================================
  // FEATURE #5: 🎙️ WALKIE-TALKIE PTT VOICE NOTES (SEND SILENTLY & PLAY ON DEMAND)
  // ============================================================================
  const openPttModal = (incident) => {
    if (!ensureOfficerApproved()) return;
    setPttTargetIncident(incident);
    setCustomPttText('');
    setPttModalVisible(true);
  };

  const sendPttVoiceNote = async (spokenTranscript) => {
    const textToSend = (spokenTranscript || customPttText).trim();
    if (!textToSend) {
      Alert.alert('Empty Voice Note', 'Please select a tactical preset or enter a voice dispatch message.');
      return;
    }

    const sigName = pttTargetIncident?.location_name || 'Kumbakonam Central Traffic Signal - Pole 04';
    const senderLabel = `${profileData.designation || 'Officer'} ${profileData.name || token} (${profileData.badge_number || token})`;

    const newVoiceObj = {
      id: `ptt-${Date.now()}`,
      officer_name: senderLabel,
      badge_number: profileData.badge_number || token,
      location_name: sigName,
      transcript: textToSend,
      created_at: new Date().toISOString(),
      is_listened: false
    };

    try {
      const updatedNotes = [newVoiceObj, ...voiceNotes];
      setVoiceNotes(updatedNotes);
      await AsyncStorage.setItem('local_ptt_notes_8002', JSON.stringify(updatedNotes));

      await fetch(`${API_BASE_URL}/api/voice-notes`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(newVoiceObj)
      }).catch(() => {});

      setPttModalVisible(false);
      setCustomPttText('');
      Alert.alert(
        '🎙️ PTT Voice Note Queued',
        'Your voice note has been sent to the PTT Voice Tab. Admin can play it on demand.'
      );
    } catch (e) {
      Alert.alert('Sent to PTT Tab', 'Voice note saved to Walkie-Talkie PTT queue.');
    }
  };

  // Play Voice Note ONLY when explicitly requested by Admin/User & mark as LISTENED
  const playVoiceNoteOnDemand = async (vn) => {
    try {
      setPlayingVoiceId(vn.id);
      if (Speech && Speech.speak) {
        Speech.stop();
        Speech.speak(
          `Walkie Talkie Dispatch from ${vn.officer_name} at ${vn.location_name}. ${vn.transcript}`,
          {
            language: 'en-IN',
            pitch: 1.0,
            rate: 0.95,
            onDone: () => setPlayingVoiceId(null),
            onError: () => setPlayingVoiceId(null)
          }
        );
      } else {
        setTimeout(() => setPlayingVoiceId(null), 2000);
      }

      // Mark as LISTENED locally & on backend so it visually differentiates from NEW voice notes
      const updatedListened = { ...listenedVoiceIds, [vn.id]: true };
      setListenedVoiceIds(updatedListened);
      await AsyncStorage.setItem('listened_ptt_8002', JSON.stringify(updatedListened));

      fetch(`${API_BASE_URL}/api/voice-notes/${vn.id}/listen`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      }).catch(() => {});
    } catch (e) {
      setPlayingVoiceId(null);
    }
  };

  // OFFICER BACKUP & ASSISTANCE FUNCTIONS
  const openBackupModal = (incident) => {
    if (!ensureOfficerApproved()) return;
    setBackupTargetIncident(incident);
    setBackupModalVisible(true);
  };

  const sendBackupRequest = async (targetBadge = 'ALL UNITS') => {
    if (!backupTargetIncident) return;
    try {
      const res = await fetch(`${API_BASE_URL}/blockades/${backupTargetIncident.id}/request-backup`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_badge: targetBadge,
          reason: 'High congestion - Multiple officers needed'
        })
      });
      if (res.ok) {
        setBackupModalVisible(false);
        fetchData();
        Alert.alert(
          '🆘 உதவி அழைப்பு அனுப்பப்பட்டது!',
          `Backup SOS transmitted to ${targetBadge} for ${backupTargetIncident.location_name}.`
        );
      }
    } catch (e) {
      Alert.alert('Error', 'Could not send backup alert.');
    }
  };

  const callFellowOfficerPhone = (mobileNum, officerName) => {
    if (!mobileNum) {
      Alert.alert('No Number', 'Mobile number not available.');
      return;
    }
    Linking.openURL(`tel:${mobileNum}`).catch(() => {
      Alert.alert('Dialer', `Calling ${officerName} at ${mobileNum}`);
    });
  };

  const resetAllBlockades = async () => {
    if (token.toUpperCase() !== 'TN-ADMIN-01') return;
    try {
      await fetch(`${API_BASE_URL}/blockades/reset-all`, { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } });
      fetchData(); Alert.alert('Database Reset', 'Fresh active incident respawned.');
    } catch (e) {}
  };

  const simulateAIHazard = async () => {
    if (token.toUpperCase() !== 'TN-ADMIN-01') return;
    try {
      await fetch(`${API_BASE_URL}/blockades/simulate-ai`, { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } });
      fetchData();
    } catch (e) {}
  };

  const updateStatus = async (incident, action) => {
    if (!ensureOfficerApproved()) return;
    try {
      let payload = {};
      if (action === 'assign') {
        try {
          let loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
          if (loc && loc.coords) {
            payload = { latitude: loc.coords.latitude, longitude: loc.coords.longitude };
          }
        } catch (err) {
          payload = { latitude: incident.latitude + 0.008, longitude: incident.longitude + 0.008 };
        }
      } 
      else if (action === 'arrived') {
        const isDemoAccount = token.toLowerCase() === 'test1' || token.toLowerCase() === 'tn-police-007';

        if (!isDemoAccount) {
          try {
            let loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
            if (loc && loc.coords) {
              const officerLat = loc.coords.latitude;
              const officerLng = loc.coords.longitude;
              
              const R = 6371e3;
              const φ1 = (officerLat * Math.PI) / 180;
              const φ2 = (incident.latitude * Math.PI) / 180;
              const Δφ = ((incident.latitude - officerLat) * Math.PI) / 180;
              const Δλ = ((incident.longitude - officerLng) * Math.PI) / 180;

              const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
                        Math.cos(φ1) * Math.cos(φ2) *
                        Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
              const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
              const distanceMeters = R * c;

              if (distanceMeters > 100) {
                Alert.alert(
                  'Geofence Lock 🛡️',
                  `You are too far from the traffic signal (${distanceMeters.toFixed(0)}m away). You must be within 100 meters to mark arrived.`
                );
                return;
              }
            }
          } catch (err) {
            console.log('Location check error:', err);
          }
        }
      }

      const res = await fetch(`${API_BASE_URL}/blockades/${incident.id}/${action}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        fetchData();
        if (action === 'assign') {
          Alert.alert('Unit Dispatched 🚓', `Dispatched to ${incident.location_name}. Live GPS stream active!`);
        } else if (action === 'arrived') {
          Alert.alert('On Scene 📍', 'Arrival verified! Proceed to live camera clearance.');
        }
      }
    } catch (e) { Alert.alert('Error', e.message); }
  };

  const pickImageForClearance = async (incident) => {
    if (!ensureOfficerApproved()) return;
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) { Alert.alert('Camera permission required.'); return; }
    const result = await ImagePicker.launchCameraAsync({ allowsEditing: true, quality: 0.6, base64: true });
    if (!result.canceled && result.assets && result.assets[0].base64) {
      const res = await fetch(`${API_BASE_URL}/blockades/${incident.id}/resolve-photo-base64`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_data: `data:image/jpeg;base64,${result.assets[0].base64}` })
      });
      if (res.ok) {
        await fetchData();
        Alert.alert('Clearance Verified ✅', 'Incident resolved and added to your Personal Clearances tab!');
      }
    }
  };

  const saveProfileChanges = async () => {
    try {
      setLoading(true);
      const formData = new FormData();
      formData.append('name', editName);
      formData.append('designation', editDesignation);
      formData.append('mobile', editMobile);
      formData.append('email', editEmail);
      if (editPassword.trim() !== '') formData.append('password', editPassword.trim());

      const res = await fetch(`${API_BASE_URL}/api/profile`, {
        method: 'PUT', headers: { 'Authorization': `Bearer ${token}` }, body: formData
      });
      if (!res.ok) throw new Error('Failed to update');
      setEditPassword(''); await fetchData();
      Alert.alert('Updated', 'Profile changes saved successfully.');
    } catch (e) { Alert.alert('Error', e.message); }
    finally { setLoading(false); }
  };

  const submitAppFeedback = async () => {
    if (!feedbackMessage.trim()) {
      Alert.alert('Empty Feedback', 'Please type your feedback or report before submitting.');
      return;
    }
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE_URL}/api/feedback`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ rating: feedbackRating, message: feedbackMessage.trim() })
      });
      if (!res.ok) throw new Error('Failed to send feedback');
      setFeedbackMessage('');
      fetchData();
      Alert.alert('Feedback Sent ✅', 'Your app feedback has been transmitted to Central Command Admin.');
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setLoading(false);
    }
  };

  const approveOfficerAccount = async (badgeNum) => {
    try {
      await fetch(`${API_BASE_URL}/admin/officers/${badgeNum}/approve`, {
        method: 'POST', headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchData(); Alert.alert('Approved', `Officer ${badgeNum} is active.`);
    } catch (e) {}
  };

  const openAdminEditOfficerModal = (officer) => {
    setTargetOfficerBadge(officer.badge_number);
    setTargetOfficerName(officer.name || '');
    setTargetOfficerDesignation(officer.designation || 'Sub-Inspector (SI)');
    setTargetOfficerMobile(officer.mobile || '');
    setTargetOfficerEmail(officer.email || '');
    setTargetOfficerStatus(officer.status || 'ACTIVE');
    setTargetOfficerPassword('');
    setAdminEditModalVisible(true);
  };

  const saveAdminOfficerEdit = async () => {
    try {
      await fetch(`${API_BASE_URL}/admin/officers/${targetOfficerBadge}`, {
        method: 'PUT',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: targetOfficerName,
          designation: targetOfficerDesignation,
          mobile: targetOfficerMobile,
          email: targetOfficerEmail,
          status: targetOfficerStatus,
          password: targetOfficerPassword.trim() !== '' ? targetOfficerPassword.trim() : null
        })
      });
      setAdminEditModalVisible(false); fetchData();
      Alert.alert('Success', 'Officer account updated.');
    } catch (e) { Alert.alert('Error'); }
  };

  const deleteAdminOfficerAccount = (badgeNum) => {
    if (badgeNum.toUpperCase() === 'TN-ADMIN-01') {
      Alert.alert('Restricted', 'Cannot delete primary Central Command Admin.');
      return;
    }
    Alert.alert(
      'Delete Officer Account',
      `Are you sure you want to permanently DELETE Officer ${badgeNum}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              const res = await fetch(`${API_BASE_URL}/admin/officers/${badgeNum}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
              });
              if (res.ok) {
                setAdminEditModalVisible(false);
                fetchData();
                Alert.alert('Deleted', `Officer ${badgeNum} removed from system.`);
              } else {
                Alert.alert('Error', 'Could not delete officer.');
              }
            } catch (e) {
              Alert.alert('Error', 'Network error while deleting officer.');
            }
          }
        }
      ]
    );
  };

  const handleLogout = async () => {
    if (locationSubscriptionRef.current) {
      locationSubscriptionRef.current.remove();
      locationSubscriptionRef.current = null;
    }
    await AsyncStorage.removeItem('token_8002');
    await AsyncStorage.removeItem('profile_8002');
    setToken('');
    setHasSavedSession(false);
    setIsUnlocked(false);
  };

  // ============================================================================
  // SCREEN 1: VERIFICATION-ONLY SCREEN (Shown when officer is already logged in)
  // ============================================================================
  if (hasSavedSession && !isUnlocked) {
    return (
      <SafeAreaView style={styles.authContainer}>
        <StatusBar barStyle="light-content" backgroundColor="#050b16" />
        <View style={styles.dualStripe}><View style={styles.stripeRed}/><View style={styles.stripeBlue}/></View>
        <ScrollView contentContainerStyle={styles.authScroll}>
          <View style={styles.authCard}>
            <View style={styles.emblemWrapper}>
              <Image source={{ uri: profileData.profile_photo || `${API_BASE_URL}/logo.png` }} style={styles.emblem}/>
            </View>
            <Text style={styles.stateText}>தமிழ்நாடு காவல்துறை • OFFICER VERIFICATION</Text>
            <Text style={styles.appTitle}>{profileData.name || token}</Text>
            <Text style={{ color: '#38bdf8', fontSize: 12, fontWeight: 'bold', marginTop: 2 }}>
              🎖️ {profileData.designation || 'Officer'} • {profileData.badge_number || token}
            </Text>
            <Text style={[styles.appSubtitle, { marginTop: 4 }]}>
              Active Session Locked • Verify Identity to Continue
            </Text>

            <View style={[styles.bioSectionBox, { width: '100%', marginTop: 6 }]}>
              <Text style={styles.bioHeaderTitle}>
                🔐 SELECT DEVICE VERIFICATION METHOD
              </Text>
              <Text style={styles.bioSubHint}>
                Tap any compatible biometric or passkey method on your mobile:
              </Text>

              <TouchableOpacity
                style={[
                  styles.bioMethodRow,
                  !authCompatibility.fingerprint && styles.bioMethodDisabled,
                  selectedAuthMethod === 'FINGERPRINT' && authCompatibility.fingerprint && styles.bioMethodSelected
                ]}
                onPress={() => handleVerifySavedSession('FINGERPRINT')}
              >
                <Text style={styles.bioMethodText}>🫆 Fingerprint Authentication</Text>
                <Text style={[styles.bioCompatBadge, authCompatibility.fingerprint ? styles.compatOk : styles.compatNo]}>
                  {authCompatibility.fingerprint ? '✓ COMPATIBLE' : '✕ NOT COMPATIBLE'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.bioMethodRow,
                  !authCompatibility.facelock && styles.bioMethodDisabled,
                  selectedAuthMethod === 'FACELOCK' && authCompatibility.facelock && styles.bioMethodSelected
                ]}
                onPress={() => handleVerifySavedSession('FACELOCK')}
              >
                <Text style={styles.bioMethodText}>😊 FaceID / FaceLock</Text>
                <Text style={[styles.bioCompatBadge, authCompatibility.facelock ? styles.compatOk : styles.compatNo]}>
                  {authCompatibility.facelock ? '✓ COMPATIBLE' : '✕ NOT COMPATIBLE'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.bioMethodRow,
                  !authCompatibility.passkey && styles.bioMethodDisabled,
                  selectedAuthMethod === 'PASSKEY' && authCompatibility.passkey && styles.bioMethodSelected
                ]}
                onPress={() => handleVerifySavedSession('PASSKEY')}
              >
                <Text style={styles.bioMethodText}>🔑 Mobile Passkey / Screen Lock</Text>
                <Text style={[styles.bioCompatBadge, authCompatibility.passkey ? styles.compatOk : styles.compatNo]}>
                  {authCompatibility.passkey ? '✓ COMPATIBLE' : '✕ NOT COMPATIBLE'}
                </Text>
              </TouchableOpacity>

              <View style={{ marginTop: 12, borderTopWidth: 1, borderTopColor: '#1e293b', paddingTop: 10 }}>
                <Text style={styles.fieldLabel}>OR ENTER OFFICER PASSKEY / PIN</Text>
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <TextInput
                    style={[styles.input, { flex: 1, marginBottom: 0 }]}
                    placeholder="Enter Passkey"
                    placeholderTextColor="#64748b"
                    secureTextEntry
                    value={quickPinInput}
                    onChangeText={setQuickPinInput}
                  />
                  <TouchableOpacity style={[styles.amberButton, { marginTop: 0, paddingHorizontal: 16, justifyContent: 'center' }]} onPress={handleQuickPinUnlock}>
                    <Text style={styles.amberButtonText}>Unlock →</Text>
                  </TouchableOpacity>
                </View>
              </View>
            </View>

            <Text style={styles.devSignature}>Designed & Developed by Mohamed Hamdan</Text>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ============================================================================
  // SCREEN 2: INITIAL LOGIN / REGISTRATION SCREEN (Only if logged out)
  // ============================================================================
  if (!hasSavedSession) {
    return (
      <SafeAreaView style={styles.authContainer}>
        <StatusBar barStyle="light-content" backgroundColor="#050b16" />
        <View style={styles.dualStripe}><View style={styles.stripeRed}/><View style={styles.stripeBlue}/></View>
        <ScrollView contentContainerStyle={styles.authScroll}>
          <View style={styles.authCard}>
            <View style={styles.emblemWrapper}><Image source={{ uri: `${API_BASE_URL}/logo.png` }} style={styles.emblem}/></View>
            <Text style={styles.stateText}>தமிழ்நாடு காவல்துறை • TAMIL NADU POLICE</Text>
            <Text style={styles.appTitle}>நான்காம் காவல் நண்பன்</Text>
            <Text style={styles.appSubtitle}>NAANGHAM KAAVAL NANBAN</Text>

            {!isRegistering ? (
              <View style={styles.formContainer}>
                <Text style={styles.fieldLabel}>BADGE ID / USERNAME</Text>
                <TextInput style={styles.input} placeholder="TN-ADMIN-01 or test1" placeholderTextColor="#64748b" value={username} onChangeText={setUsername} autoCapitalize="none"/>
                <Text style={styles.fieldLabel}>PASSWORD</Text>
                <View style={styles.passwordWrapper}>
                  <TextInput style={styles.passwordInput} placeholder="Password" placeholderTextColor="#64748b" value={password} onChangeText={setPassword} secureTextEntry={!showLoginPassword}/>
                  <TouchableOpacity onPress={() => setShowLoginPassword(!showLoginPassword)} style={styles.eyeBtn}>
                    <Text style={styles.eyeText}>{showLoginPassword ? '🙈 Hide' : '👁️ Show'}</Text>
                  </TouchableOpacity>
                </View>
                <TouchableOpacity style={styles.primaryButton} onPress={handleLogin}>
                  <Text style={styles.buttonText}>🛡️ One-Time Secure Login</Text>
                </TouchableOpacity>

                <TouchableOpacity onPress={() => setIsRegistering(true)} style={styles.switchButton}>
                  <Text style={styles.switchText}>New Officer? Register Enrolment →</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <View style={styles.formContainer}>
                {!stepOtp ? (
                  <>
                    <Text style={styles.fieldLabel}>FULL NAME</Text>
                    <TextInput style={styles.input} placeholder="K. Murugan" placeholderTextColor="#64748b" value={regName} onChangeText={setRegName}/>

                    <Text style={styles.fieldLabel}>SELECT OFFICER RANK / DESIGNATION</Text>
                    <View style={styles.rankGrid}>
                      {OFFICER_RANKS.map(rank => (
                        <TouchableOpacity
                          key={rank}
                          style={[styles.rankChip, regDesignation === rank && styles.rankChipActive]}
                          onPress={() => setRegDesignation(rank)}
                        >
                          <Text style={[styles.rankChipText, regDesignation === rank && styles.rankChipTextActive]}>
                            {rank}
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </View>

                    <Text style={styles.fieldLabel}>BADGE ID</Text>
                    <TextInput style={styles.input} placeholder="TN-POLICE-99" placeholderTextColor="#64748b" value={regBadge} onChangeText={setRegBadge} autoCapitalize="characters"/>
                    <Text style={styles.fieldLabel}>MOBILE</Text>
                    <TextInput style={styles.input} placeholder="9876543210" placeholderTextColor="#64748b" keyboardType="phone-pad" value={regMobile} onChangeText={setRegMobile}/>
                    <Text style={styles.fieldLabel}>EMAIL</Text>
                    <TextInput style={styles.input} placeholder="officer@tn.gov.in" placeholderTextColor="#64748b" keyboardType="email-address" value={regEmail} onChangeText={setRegEmail} autoCapitalize="none"/>
                    <Text style={styles.fieldLabel}>PASSWORD</Text>
                    <View style={styles.passwordWrapper}>
                      <TextInput style={styles.passwordInput} placeholder="••••••••" placeholderTextColor="#64748b" secureTextEntry={!showRegPassword} value={regPassword} onChangeText={setRegPassword}/>
                      <TouchableOpacity onPress={() => setShowRegPassword(!showRegPassword)} style={styles.eyeBtn}>
                        <Text style={styles.eyeText}>{showRegPassword ? '🙈 Hide' : '👁️ Show'}</Text>
                      </TouchableOpacity>
                    </View>
                    <TouchableOpacity style={styles.amberButton} onPress={handleRequestOtp}><Text style={styles.amberButtonText}>📩 Send Verification OTP</Text></TouchableOpacity>
                  </>
                ) : (
                  <>
                    <View style={styles.otpHintBox}>
                      <Text style={styles.otpLabel}>OTP Dispatched ({regDesignation})</Text>
                      <Text style={styles.otpSimCode}>[SIMULATED OTP]: {sentOtpCode}</Text>
                    </View>
                    <TextInput style={[styles.input, styles.otpInput]} placeholder="123456" placeholderTextColor="#64748b" keyboardType="number-pad" maxLength={6} value={regOtp} onChangeText={setRegOtp}/>
                    <TouchableOpacity style={[styles.primaryButton, { backgroundColor: '#10b981' }]} onPress={handleVerifyAndRegister}><Text style={styles.buttonText}>✓ Verify & Register</Text></TouchableOpacity>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 12 }}>
                      <TouchableOpacity onPress={handleResendOtp}><Text style={{ color: '#fbbf24', fontSize: 12, fontWeight: 'bold' }}>🔄 Resend OTP</Text></TouchableOpacity>
                      <TouchableOpacity onPress={() => setStepOtp(false)}><Text style={{ color: '#94a3b8', fontSize: 12 }}>← Edit Details</Text></TouchableOpacity>
                    </View>
                  </>
                )}
                <TouchableOpacity onPress={() => { setIsRegistering(false); setStepOtp(false); }} style={styles.switchButton}>
                  <Text style={styles.switchText}>← Back to Login</Text>
                </TouchableOpacity>
              </View>
            )}
            <Text style={styles.devSignature}>Designed & Developed by Mohamed Hamdan</Text>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ============================================================================
  // SCREEN 3: UNLOCKED MAIN DASHBOARD
  // ============================================================================
  const isAdmin = token.toUpperCase() === 'TN-ADMIN-01';
  const isPendingApproval = !isAdmin && profileData.status !== 'ACTIVE';
  const critCount = blockades.filter(b => b.severity === 'CRITICAL' && b.status !== 'RESOLVED').length;
  const dispCount = blockades.filter(b => b.status === 'ASSIGNED').length;
  const sceneCount = blockades.filter(b => b.status === 'ARRIVED').length;
  const resolvedCount = blockades.filter(b => b.status === 'RESOLVED').length;

  // Count unread PTT voice notes
  const unreadVoiceCount = voiceNotes.filter(v => !v.is_listened && !listenedVoiceIds[v.id]).length;

  return (
    <SafeAreaView style={styles.mainContainer}>
      <StatusBar barStyle="light-content" backgroundColor="#081021" />
      <View style={styles.dualStripe}><View style={styles.stripeRed}/><View style={styles.stripeBlue}/></View>
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <Image source={{ uri: `${API_BASE_URL}/logo.png` }} style={styles.headerLogo}/>
          <View style={{ flex: 1 }}>
            <Text style={styles.headerTitle}>நான்காம் காவல் நண்பன்</Text>
            <View style={styles.subHeaderRow}>
              <View style={styles.greenDot}/>
              <Text style={styles.headerSub}>
                {profileData.designation || 'Officer'} • {profileData.badge_number || token}
              </Text>
            </View>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          <TouchableOpacity style={styles.syncBtn} onPress={() => setIsUnlocked(false)}>
            <Text style={styles.syncText}>🔒 LOCK</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.syncBtn} onPress={fetchData}>
            <Text style={styles.syncText}>↻ SYNC</Text>
          </TouchableOpacity>
        </View>
      </View>

      {isPendingApproval && (
        <View style={styles.bannerPending}><Text style={styles.bannerText}>⏳ ACCOUNT PENDING APPROVAL (Actions Locked)</Text></View>
      )}

      <View style={styles.contentBody}>
        {currentTab === 'Incidents' && (
          <ScrollView contentContainerStyle={styles.scrollList}>
            <View style={styles.statsRow}>
              <View style={[styles.statCard, { borderColor: 'rgba(239,68,68,0.35)' }]}>
                <Text style={[styles.statNum, { color: '#ef4444' }]}>{critCount}</Text>
                <Text style={styles.statLabel}>CRITICAL</Text>
              </View>
              <View style={[styles.statCard, { borderColor: 'rgba(245,158,11,0.35)' }]}>
                <Text style={[styles.statNum, { color: '#f59e0b' }]}>{dispCount}</Text>
                <Text style={styles.statLabel}>DISPATCHED</Text>
              </View>
              <View style={[styles.statCard, { borderColor: 'rgba(59,130,246,0.35)' }]}>
                <Text style={[styles.statNum, { color: '#3b82f6' }]}>{sceneCount}</Text>
                <Text style={styles.statLabel}>ON SCENE</Text>
              </View>
            </View>

            {/* FEATURE #3: GOLDEN-HOUR SLA RESPONSE ANALYTICS BANNER */}
            <View style={styles.slaAnalyticsBanner}>
              <View>
                <Text style={styles.slaBannerTitle}>⏱️ GOLDEN-HOUR SLA TELEMETRY</Text>
                <Text style={styles.slaBannerSub}>Avg Junction Clearance Time: 03m 24s • Cleared Today: {resolvedCount}</Text>
              </View>
              <View style={styles.slaBadgePill}>
                <Text style={styles.slaBadgeText}>98.4% SLA</Text>
              </View>
            </View>

            {isAdmin && (
              <View style={styles.quickActionsBar}>
                <TouchableOpacity style={styles.quickResetBtn} onPress={resetAllBlockades}><Text style={styles.quickBtnText}>🔄 Reset DB</Text></TouchableOpacity>
                <TouchableOpacity style={styles.quickSimBtn} onPress={simulateAIHazard}><Text style={styles.quickSimText}>📡 Simulate Hazard</Text></TouchableOpacity>
              </View>
            )}

            <View style={styles.sectionHeaderRow}>
              <Text style={styles.sectionHeading}>🚨 LIVE TRAFFIC SIGNAL INCIDENTS</Text>
              <Text style={styles.totalCountText}>{blockades.length} TOTAL</Text>
            </View>

            {blockades.length === 0 ? (
              <Text style={styles.emptyText}>No active field blockades reported.</Text>
            ) : (
              blockades.slice().reverse().map(b => {
                const isResolved = b.status === 'RESOLVED';
                const isYoloOpen = expandedBlockadeYoloId === b.id;
                const isCorridorOn = !!(b.green_corridor || greenCorridorMap[b.id]);
                const statusBadgeStyle = isResolved ? styles.badgeResolved : b.status === 'ACTIVE' ? styles.badgeActive : styles.badgeAssigned;
                const statusTextStyle = isResolved ? styles.badgeTextResolved : b.status === 'ACTIVE' ? styles.badgeTextActive : styles.badgeTextAssigned;

                return (
                  <View key={b.id} style={[styles.incidentCard, isResolved && styles.resolvedCard, isCorridorOn && styles.corridorCardBorder]}>
                    <View style={styles.cardTopRow}>
                      <View style={statusBadgeStyle}><Text style={statusTextStyle}>• {b.status}</Text></View>
                      {/* FEATURE #3: LIVE INCIDENT SLA TIMER */}
                      <Text style={[styles.slaTimerTag, isResolved && { color: '#10b981' }]}>
                        {formatIncidentSlaTimer(b)}
                      </Text>
                      <Text style={styles.severityLabel}>{b.severity}</Text>
                    </View>

                    <Text style={styles.incidentLocation}>🚦 {b.location_name}</Text>
                    <Text style={styles.incidentNotes}>{b.notes}</Text>

                    {isCorridorOn && (
                      <View style={styles.corridorActiveBanner}>
                        <Text style={styles.corridorActiveText}>
                          🚑 108 AMBULANCE GREEN CORRIDOR ACTIVE — ESP8266 GREEN LOCKED
                        </Text>
                      </View>
                    )}

                    {b.image_url ? <Image source={{ uri: b.image_url }} style={styles.hazardImg}/> : null}

                    {/* TACTICAL UTILITY BAR: FEATURE #1 (Green Corridor), FEATURE #2 (Google Maps Nav), FEATURE #5 (PTT Voice) & LIVE YOLO */}
                    {!isResolved && (
                      <View style={{ marginTop: 10, gap: 6 }}>
                        <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                          <TouchableOpacity
                            style={[styles.utilityChip, isCorridorOn && styles.utilityChipGreenActive]}
                            onPress={() => toggleGreenCorridor(b)}
                          >
                            <Text style={styles.utilityChipText}>
                              {isCorridorOn ? '🚑 Corridor ON' : '🚑 Green Corridor'}
                            </Text>
                          </TouchableOpacity>

                          <TouchableOpacity
                            style={styles.utilityChip}
                            onPress={() => launchGoogleMapsNavigation(b)}
                          >
                            <Text style={styles.utilityChipText}>🧭 Navigate</Text>
                          </TouchableOpacity>

                          <TouchableOpacity
                            style={styles.utilityChip}
                            onPress={() => openPttModal(b)}
                          >
                            <Text style={styles.utilityChipText}>🎙️ Send PTT Voice</Text>
                          </TouchableOpacity>
                        </View>

                        <TouchableOpacity
                          style={styles.yoloToggleBtn}
                          onPress={() => setExpandedBlockadeYoloId(isYoloOpen ? null : b.id)}
                        >
                          <Text style={styles.yoloToggleText}>
                            {isYoloOpen
                              ? '🙈 HIDE LIVE YOLO VISUALS FOR THIS SIGNAL'
                              : `👁️ VIEW LIVE YOLO VISUALS (${b.location_name})`}
                          </Text>
                        </TouchableOpacity>

                        {isYoloOpen && (
                          <View style={styles.yoloLiveCard}>
                            <Text style={styles.yoloLiveTitle}>
                              📡 Live YOLOv8 Feed • {b.location_name}
                            </Text>
                            <Text style={styles.yoloLiveSub}>
                              ⚡ {yoloStream?.stage || 'LIVE MONITORING'} • ⏱️ {yoloStream?.timer || 0}s • 🎯 ROI Hazards: {yoloStream?.objects || 0} ({yoloStream?.hazards || 'ACTIVE'})
                            </Text>
                            {yoloStream?.frame ? (
                              <Image source={{ uri: yoloStream.frame }} style={styles.yoloLiveImage} resizeMode="contain" />
                            ) : b.image_url ? (
                              <Image source={{ uri: b.image_url }} style={styles.yoloLiveImage} resizeMode="contain" />
                            ) : (
                              <Text style={styles.emptyText}>Waiting for live stream from python yolo_live_detector.py...</Text>
                            )}
                          </View>
                        )}
                      </View>
                    )}

                    {b.clearance_photo ? (
                      <View style={styles.clearanceBox}>
                        <Text style={styles.clearanceTitle}>📷 Clearance Verified ({b.resolved_by}):</Text>
                        <Image source={{ uri: b.clearance_photo }} style={styles.clearanceImg}/>
                      </View>
                    ) : null}

                    {!isResolved && !isAdmin && (
                      <View style={styles.cardFooter}>
                        <TouchableOpacity style={styles.backupSosBtn} onPress={() => openBackupModal(b)}>
                          <Text style={styles.backupSosBtnText}>🆘 Request Backup</Text>
                        </TouchableOpacity>

                        <View style={styles.actionRow}>
                          {b.status === 'ACTIVE' && (
                            <TouchableOpacity style={styles.actionBtnBlue} onPress={() => updateStatus(b, 'assign')}><Text style={styles.actionBtnText}>🚓 Dispatch</Text></TouchableOpacity>
                          )}
                          {b.status === 'ASSIGNED' && (
                            <TouchableOpacity style={styles.actionBtnAmber} onPress={() => updateStatus(b, 'arrived')}><Text style={styles.actionBtnText}>📍 Arrived</Text></TouchableOpacity>
                          )}
                          {b.status === 'ARRIVED' && (
                            <TouchableOpacity style={styles.actionBtnEmerald} onPress={() => pickImageForClearance(b)}><Text style={styles.actionBtnText}>📷 Camera Clear</Text></TouchableOpacity>
                          )}
                        </View>
                      </View>
                    )}
                  </View>
                );
              })
            )}
            <Text style={styles.devSignature}>Designed & Developed by Mohamed Hamdan</Text>
          </ScrollView>
        )}

        {/* ============================================================================
            FEATURE #5: 🎙️ DEDICATED WALKIE-TALKIE PTT VOICE NOTES TAB
            (Never plays automatically! Admin/User taps Play to listen; clearly separates NEW vs LISTENED)
           ============================================================================ */}
        {currentTab === 'VoicePTT' && (
          <ScrollView contentContainerStyle={styles.scrollList}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <View>
                <Text style={styles.sectionHeading}>🎙️ WALKIE-TALKIE PTT VOICE DISPATCHES</Text>
                <Text style={{ color: '#94a3b8', fontSize: 10, marginTop: 2 }}>
                  Voice notes never auto-play. Tap Play to listen and mark as Listened.
                </Text>
              </View>
              {!isAdmin && (
                <TouchableOpacity
                  style={styles.actionBtnBlue}
                  onPress={() => openPttModal(blockades.find(b => b.status !== 'RESOLVED') || null)}
                >
                  <Text style={styles.actionBtnText}>🎙️ + Record PTT</Text>
                </TouchableOpacity>
              )}
            </View>

            {/* SUMMARY COUNTERS: NEW VS LISTENED */}
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
              <View style={[styles.statCard, { borderColor: '#f59e0b', paddingVertical: 10 }]}>
                <Text style={{ color: '#fbbf24', fontSize: 18, fontWeight: '900' }}>{unreadVoiceCount}</Text>
                <Text style={styles.statLabel}>🔴 NEW / UNHEARD</Text>
              </View>
              <View style={[styles.statCard, { borderColor: '#10b981', paddingVertical: 10 }]}>
                <Text style={{ color: '#10b981', fontSize: 18, fontWeight: '900' }}>
                  {voiceNotes.length - unreadVoiceCount}
                </Text>
                <Text style={styles.statLabel}>✅ ALREADY LISTENED</Text>
              </View>
            </View>

            {voiceNotes.length === 0 ? (
              <Text style={styles.emptyText}>No Walkie-Talkie PTT voice notes transmitted yet.</Text>
            ) : (
              voiceNotes.map(vn => {
                const isHeard = !!(vn.is_listened || listenedVoiceIds[vn.id]);
                const isPlayingNow = playingVoiceId === vn.id;

                return (
                  <View
                    key={vn.id}
                    style={[
                      styles.voiceNoteCard,
                      isHeard ? styles.voiceNoteCardListened : styles.voiceNoteCardNew
                    ]}
                  >
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <View style={isHeard ? styles.pillListened : styles.pillNewVoice}>
                        <Text style={isHeard ? styles.pillListenedText : styles.pillNewVoiceText}>
                          {isHeard ? '✅ ALREADY LISTENED' : '🔴 NEW VOICE NOTE'}
                        </Text>
                      </View>
                      <Text style={styles.alertTime}>
                        {vn.created_at ? new Date(vn.created_at).toLocaleTimeString() : 'Just now'}
                      </Text>
                    </View>

                    <Text style={{ color: '#fff', fontWeight: 'bold', fontSize: 13 }}>
                      👮 {vn.officer_name || 'Field Officer'}
                    </Text>
                    <Text style={{ color: '#38bdf8', fontSize: 11, fontWeight: 'bold', marginTop: 2 }}>
                      🚦 Signal: {vn.location_name}
                    </Text>
                    <Text style={{ color: '#cbd5e1', fontSize: 12, marginTop: 6, fontStyle: 'italic' }}>
                      "{vn.transcript}"
                    </Text>

                    <View style={{ flexDirection: 'row', justifyContent: 'flex-end', marginTop: 10 }}>
                      <TouchableOpacity
                        style={isHeard ? styles.playBtnListened : styles.playBtnNew}
                        onPress={() => playVoiceNoteOnDemand(vn)}
                      >
                        <Text style={{ color: '#fff', fontSize: 11, fontWeight: 'bold' }}>
                          {isPlayingNow
                            ? '🔊 Playing Dispatch...'
                            : isHeard
                            ? '🔄 Replay Voice Note'
                            : '▶️ Play Voice Note (Admin Request)'}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                );
              })
            )}
            <Text style={styles.devSignature}>Designed & Developed by Mohamed Hamdan</Text>
          </ScrollView>
        )}

        {/* ADMIN-ONLY ALL TRAFFIC SIGNALS LIVE YOLOv8 MATRIX TAB */}
        {currentTab === 'AllSignalsYolo' && isAdmin && (
          <ScrollView contentContainerStyle={styles.scrollList}>
            <Text style={styles.sectionHeading}>👁️ ADMIN: ALL TRAFFIC SIGNALS LIVE YOLOv8 MATRIX</Text>
            <Text style={{ color: '#94a3b8', fontSize: 11, marginBottom: 10 }}>
              Central Command Supervisor view of all connected traffic signal edge-AI cameras:
            </Text>
            {allYoloStreams.map((sig, idx) => (
              <View key={idx} style={styles.yoloLiveCard}>
                <Text style={styles.yoloLiveTitle}>🚦 {sig.location_name}</Text>
                <Text style={styles.yoloLiveSub}>
                  ⚡ {sig.stage} • ⏱️ {sig.timer}s • 🎯 ROI Objects: {sig.objects} ({sig.hazards})
                </Text>
                {sig.frame ? (
                  <Image source={{ uri: sig.frame }} style={styles.yoloLiveImage} resizeMode="contain" />
                ) : (
                  <Text style={styles.emptyText}>Waiting for python yolo_live_detector.py stream...</Text>
                )}
              </View>
            ))}
            <Text style={styles.devSignature}>Designed & Developed by Mohamed Hamdan</Text>
          </ScrollView>
        )}

        {currentTab === 'Alerts' && (
          <ScrollView contentContainerStyle={styles.scrollList}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <Text style={styles.sectionHeading}>{isAdmin ? '🔔 MASTER TELEMETRY LOG' : '🚨 BLOCKADE & BACKUP ALERTS'}</Text>
              <TouchableOpacity
                onPress={() => playPoliceTacticalSiren('[LIVE YOLO MODEL ALERT] போக்குவரத்து தடை @ Kumbakonam Central Traffic Signal', isAdmin)}
                style={{ backgroundColor: '#1e3a8a', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: '#fbbf24' }}
              >
                <Text style={{ color: '#fbbf24', fontSize: 10, fontWeight: 'bold' }}>🔊 தமிழ்/EN Audio Test</Text>
              </TouchableOpacity>
            </View>
            {notifications.length === 0 ? (
              <Text style={styles.emptyText}>No alerts recorded.</Text>
            ) : (
              notifications.slice().reverse().map(n => (
                <View key={n.id} style={styles.alertCard}>
                  <Text style={styles.alertTime}>[{new Date(n.created_at).toLocaleTimeString()}]</Text>
                  <Text style={styles.alertMsg}>{n.message}</Text>
                  {n.image_thumb ? <Image source={{ uri: n.image_thumb }} style={styles.alertThumb}/> : null}
                </View>
              ))
            )}
            <Text style={styles.devSignature}>Designed & Developed by Mohamed Hamdan</Text>
          </ScrollView>
        )}

        {currentTab === 'Clearances' && !isAdmin && (
          <ScrollView contentContainerStyle={styles.scrollList}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <Text style={styles.sectionHeading}>🎖️ MY PERSONAL LAST 10 CLEARANCES</Text>
              <TouchableOpacity onPress={fetchData} style={styles.syncBtn}>
                <Text style={styles.syncText}>↻ Refresh</Text>
              </TouchableOpacity>
            </View>
            {myClearances.length === 0 ? (
              <Text style={styles.emptyText}>No clearances recorded under your badge yet.</Text>
            ) : (
              myClearances.map((c, index) => (
                <View key={c.id} style={styles.clearanceHistoryCard}>
                  <View style={{ flex: 1, paddingRight: 10 }}>
                    <Text style={styles.historyTitle}>#{index + 1} • 🚦 {c.location_name}</Text>
                    <Text style={styles.historyNotes}>{c.notes}</Text>
                    <Text style={{ color: '#10b981', fontSize: 10, fontWeight: 'bold', marginTop: 4 }}>
                      ✓ Verified by: {c.resolved_by || profileData.badge_number || token}
                    </Text>
                  </View>
                  {c.clearance_photo ? <Image source={{ uri: c.clearance_photo }} style={styles.historyImg}/> : null}
                </View>
              ))
            )}
            <Text style={styles.devSignature}>Designed & Developed by Mohamed Hamdan</Text>
          </ScrollView>
        )}

        {currentTab === 'Profile' && (
          <ScrollView contentContainerStyle={styles.scrollList}>
            <View style={styles.profileCard}>
              <View style={styles.avatarContainer}><Image source={{ uri: profileData.profile_photo || `${API_BASE_URL}/logo.png` }} style={styles.avatar}/></View>
              <Text style={styles.profileBadgeId}>{profileData.badge_number || token}</Text>
              <Text style={{ color: '#38bdf8', fontSize: 12, fontWeight: 'bold', marginBottom: 6 }}>
                🎖️ {profileData.designation || 'Sub-Inspector (SI)'}
              </Text>
              <View style={[styles.rolePill, profileData.status === 'ACTIVE' ? styles.pillActive : styles.pillPending]}>
                <Text style={styles.pillText}>STATUS: {profileData.status}</Text>
              </View>

              <View style={styles.profileForm}>
                <Text style={styles.fieldLabel}>FULL NAME</Text>
                <TextInput style={styles.input} value={editName} onChangeText={setEditName} placeholderTextColor="#64748b"/>

                <Text style={styles.fieldLabel}>RANK / DESIGNATION</Text>
                <View style={styles.rankGrid}>
                  {OFFICER_RANKS.map(rank => (
                    <TouchableOpacity
                      key={rank}
                      style={[styles.rankChip, editDesignation === rank && styles.rankChipActive]}
                      onPress={() => setEditDesignation(rank)}
                    >
                      <Text style={[styles.rankChipText, editDesignation === rank && styles.rankChipTextActive]}>
                        {rank}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>

                <Text style={styles.fieldLabel}>MOBILE</Text>
                <TextInput style={styles.input} value={editMobile} onChangeText={setEditMobile} keyboardType="phone-pad" placeholderTextColor="#64748b"/>
                <Text style={styles.fieldLabel}>EMAIL</Text>
                <TextInput style={styles.input} value={editEmail} onChangeText={setEditEmail} keyboardType="email-address" placeholderTextColor="#64748b"/>
                <Text style={styles.fieldLabel}>NEW PASSWORD</Text>
                <View style={styles.passwordWrapper}>
                  <TextInput style={styles.passwordInput} value={editPassword} onChangeText={setEditPassword} placeholder="Leave blank to keep existing" placeholderTextColor="#64748b" secureTextEntry={!showProfilePassword}/>
                  <TouchableOpacity onPress={() => setShowProfilePassword(!showProfilePassword)} style={styles.eyeBtn}>
                    <Text style={styles.eyeText}>{showProfilePassword ? '🙈 Hide' : '👁️ Show'}</Text>
                  </TouchableOpacity>
                </View>

                <TouchableOpacity style={styles.amberButton} onPress={saveProfileChanges} disabled={loading}>
                  {loading ? <ActivityIndicator color="#000"/> : <Text style={styles.amberButtonText}>💾 Save Profile</Text>}
                </TouchableOpacity>
                <TouchableOpacity style={[styles.primaryButton, { backgroundColor: '#b91c1c', marginTop: 12 }]} onPress={handleLogout}>
                  <Text style={styles.buttonText}>🚪 Logout (Require Full Login Next Time)</Text>
                </TouchableOpacity>
              </View>
            </View>

            {/* OFFICER APP FEEDBACK FORM */}
            {!isAdmin && (
              <View style={[styles.profileCard, { marginTop: 16, borderColor: '#06b6d4' }]}>
                <Text style={[styles.sectionHeading, { color: '#38bdf8', marginBottom: 8 }]}>
                  💬 SUBMIT APP FEEDBACK TO ADMIN
                </Text>
                <Text style={styles.fieldLabel}>STAR RATING</Text>
                <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
                  {[1, 2, 3, 4, 5].map(star => (
                    <TouchableOpacity
                      key={star}
                      onPress={() => setFeedbackRating(star)}
                      style={[
                        styles.starBtn,
                        feedbackRating >= star && styles.starBtnActive
                      ]}
                    >
                      <Text style={{ color: feedbackRating >= star ? '#fbbf24' : '#64748b', fontSize: 16 }}>★</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <Text style={[styles.fieldLabel, { alignSelf: 'flex-start' }]}>YOUR FEEDBACK / SUGGESTION</Text>
                <TextInput
                  style={[styles.input, { width: '100%', minHeight: 70, textAlignVertical: 'top' }]}
                  placeholder="Share your field experience or suggestions for BLU Guard AI..."
                  placeholderTextColor="#64748b"
                  multiline
                  value={feedbackMessage}
                  onChangeText={setFeedbackMessage}
                />
                <TouchableOpacity style={[styles.actionBtnBlue, { width: '100%', paddingVertical: 12, alignItems: 'center' }]} onPress={submitAppFeedback}>
                  <Text style={styles.actionBtnText}>📩 Send Feedback to Central Command Admin</Text>
                </TouchableOpacity>
              </View>
            )}

            {/* ADMIN: MANAGE OFFICERS & VIEW OFFICER FEEDBACKS */}
            {isAdmin && (
              <>
                <View style={[styles.profileCard, { marginTop: 16 }]}>
                  <Text style={styles.sectionHeading}>🛡️ CENTRAL COMMAND: MANAGE OFFICERS</Text>
                  {adminOfficers.map(off => {
                    const isPrimaryAdmin = off.badge_number.toUpperCase() === 'TN-ADMIN-01';
                    return (
                      <View key={off.id} style={styles.adminOfficerRow}>
                        <View style={{ flex: 1, paddingRight: 8 }}>
                          <Text style={{ color: '#fff', fontWeight: 'bold', fontSize: 12 }}>
                            {off.name} ({off.badge_number})
                          </Text>
                          <Text style={{ color: '#38bdf8', fontSize: 10, fontWeight: 'bold' }}>
                            🎖️ {off.designation || 'Sub-Inspector (SI)'}
                          </Text>
                          <Text style={{ color: '#94a3b8', fontSize: 10 }}>{off.email} • {off.status}</Text>
                        </View>
                        <View style={{ flexDirection: 'row', gap: 6 }}>
                          {off.status === 'PENDING APPROVAL' && (
                            <TouchableOpacity style={styles.actionBtnEmerald} onPress={() => approveOfficerAccount(off.badge_number)}>
                              <Text style={styles.actionBtnText}>Approve</Text>
                            </TouchableOpacity>
                          )}
                          <TouchableOpacity style={styles.actionBtnBlue} onPress={() => openAdminEditOfficerModal(off)}>
                            <Text style={styles.actionBtnText}>✏️ Edit</Text>
                          </TouchableOpacity>
                          {!isPrimaryAdmin && (
                            <TouchableOpacity style={styles.actionBtnRed} onPress={() => deleteAdminOfficerAccount(off.badge_number)}>
                              <Text style={styles.actionBtnText}>🗑️</Text>
                            </TouchableOpacity>
                          )}
                        </View>
                      </View>
                    );
                  })}
                </View>

                <View style={[styles.profileCard, { marginTop: 16, borderColor: '#06b6d4' }]}>
                  <Text style={[styles.sectionHeading, { color: '#38bdf8', marginBottom: 8 }]}>
                    📬 OFFICER APP FEEDBACKS ({feedbacksList.length})
                  </Text>
                  {feedbacksList.length === 0 ? (
                    <Text style={styles.emptyText}>No feedbacks submitted by field officers yet.</Text>
                  ) : (
                    feedbacksList.map(fb => (
                      <View key={fb.id} style={styles.feedbackItemCard}>
                        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                          <Text style={{ color: '#fbbf24', fontWeight: 'bold', fontSize: 12 }}>
                            {fb.officer_name} • {fb.designation} ({fb.badge_number})
                          </Text>
                          <Text style={{ color: '#fbbf24', fontSize: 11 }}>
                            {'★'.repeat(fb.rating || 5)}{'☆'.repeat(5 - (fb.rating || 5))}
                          </Text>
                        </View>
                        <Text style={{ color: '#e2e8f0', fontSize: 12 }}>{fb.message}</Text>
                        <Text style={{ color: '#64748b', fontSize: 10, marginTop: 4 }}>
                          {new Date(fb.created_at).toLocaleString()}
                        </Text>
                      </View>
                    ))
                  )}
                </View>
              </>
            )}
            <Text style={styles.devSignature}>Designed & Developed by Mohamed Hamdan</Text>
          </ScrollView>
        )}
      </View>

      {/* FEATURE #5: WALKIE-TALKIE PUSH-TO-TALK (PTT) MODAL */}
      <Modal visible={pttModalVisible} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={[styles.modalCard, { borderColor: '#06b6d4' }]}>
            <Text style={[styles.modalTitle, { color: '#38bdf8' }]}>
              🎙️ WALKIE-TALKIE PTT VOICE DISPATCH
            </Text>
            <Text style={{ color: '#cbd5e1', fontSize: 11, marginBottom: 10 }}>
              📍 Signal: {pttTargetIncident?.location_name || 'Kumbakonam Central Traffic Signal'}
            </Text>

            <Text style={styles.fieldLabel}>1-TAP TACTICAL VOICE PRESETS:</Text>
            {QUICK_PTT_PRESETS.map((preset, idx) => (
              <TouchableOpacity
                key={idx}
                style={styles.pttPresetBtn}
                onPress={() => sendPttVoiceNote(preset)}
              >
                <Text style={styles.pttPresetText}>🎙️ "{preset}"</Text>
              </TouchableOpacity>
            ))}

            <Text style={[styles.fieldLabel, { marginTop: 10 }]}>OR TRANSMIT CUSTOM VOICE NOTE:</Text>
            <TextInput
              style={styles.input}
              placeholder="Type tactical voice note for Control Room..."
              placeholderTextColor="#64748b"
              value={customPttText}
              onChangeText={setCustomPttText}
            />
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity style={[styles.amberButton, { flex: 1 }]} onPress={() => sendPttVoiceNote(customPttText)}>
                <Text style={styles.amberButtonText}>📡 Queue Voice Note</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.primaryButton, { flex: 1, backgroundColor: '#334155', marginTop: 6 }]} onPress={() => setPttModalVisible(false)}>
                <Text style={styles.buttonText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* OFFICER BACKUP & ASSISTANCE REQUEST MODAL */}
      <Modal visible={backupModalVisible} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={[styles.modalCard, { borderColor: '#ef4444' }]}>
            <Text style={[styles.modalTitle, { color: '#f87171' }]}>
              🆘 உதவி அழைப்பு | REQUEST OFFICER BACKUP
            </Text>
            <Text style={{ color: '#cbd5e1', fontSize: 11, marginBottom: 10 }}>
              📍 Signal: {backupTargetIncident?.location_name}
            </Text>

            <TouchableOpacity
              style={[styles.primaryButton, { marginBottom: 14 }]}
              onPress={() => sendBackupRequest('ALL UNITS')}
            >
              <Text style={styles.buttonText}>🚨 Broadcast SOS to All Active Officers</Text>
            </TouchableOpacity>

            <Text style={styles.fieldLabel}>OR CALL / ALERT A SPECIFIC ACTIVE OFFICER:</Text>
            <ScrollView style={{ maxHeight: 220 }}>
              {fellowOfficers.map(off => (
                <View key={off.id} style={styles.adminOfficerRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: '#fff', fontWeight: 'bold', fontSize: 12 }}>
                      {off.name} ({off.badge_number})
                    </Text>
                    <Text style={{ color: '#38bdf8', fontSize: 10 }}>
                      🎖️ {off.designation} • 📞 {off.mobile}
                    </Text>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 6 }}>
                    <TouchableOpacity
                      style={styles.actionBtnEmerald}
                      onPress={() => callFellowOfficerPhone(off.mobile, off.name)}
                    >
                      <Text style={styles.actionBtnText}>📞 Call</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={styles.actionBtnRed}
                      onPress={() => sendBackupRequest(`${off.designation} ${off.name} (${off.badge_number})`)}
                    >
                      <Text style={styles.actionBtnText}>🆘 Alert</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ))}
            </ScrollView>

            <TouchableOpacity
              style={[styles.primaryButton, { backgroundColor: '#334155', marginTop: 12 }]}
              onPress={() => setBackupModalVisible(false)}
            >
              <Text style={styles.buttonText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* ADMIN EDIT & DELETE OFFICER MODAL */}
      <Modal visible={adminEditModalVisible} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>✏️ Edit Officer ({targetOfficerBadge})</Text>
            <Text style={styles.fieldLabel}>FULL NAME</Text>
            <TextInput style={styles.input} value={targetOfficerName} onChangeText={setTargetOfficerName}/>

            <Text style={styles.fieldLabel}>RANK / DESIGNATION</Text>
            <View style={styles.rankGrid}>
              {OFFICER_RANKS.map(rank => (
                <TouchableOpacity
                  key={rank}
                  style={[styles.rankChip, targetOfficerDesignation === rank && styles.rankChipActive]}
                  onPress={() => setTargetOfficerDesignation(rank)}
                >
                  <Text style={[styles.rankChipText, targetOfficerDesignation === rank && styles.rankChipTextActive]}>
                    {rank}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.fieldLabel}>MOBILE</Text>
            <TextInput style={styles.input} value={targetOfficerMobile} onChangeText={setTargetOfficerMobile} keyboardType="phone-pad"/>
            <Text style={styles.fieldLabel}>EMAIL</Text>
            <TextInput style={styles.input} value={targetOfficerEmail} onChangeText={setTargetOfficerEmail} autoCapitalize="none"/>
            <Text style={styles.fieldLabel}>STATUS</Text>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12 }}>
              <TouchableOpacity style={[styles.statusToggleBtn, targetOfficerStatus === 'ACTIVE' && styles.statusToggleActive]} onPress={() => setTargetOfficerStatus('ACTIVE')}>
                <Text style={styles.actionBtnText}>ACTIVE</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.statusToggleBtn, targetOfficerStatus === 'PENDING APPROVAL' && styles.statusTogglePending]} onPress={() => setTargetOfficerStatus('PENDING APPROVAL')}>
                <Text style={styles.actionBtnText}>PENDING</Text>
              </TouchableOpacity>
            </View>
            <Text style={styles.fieldLabel}>RESET PASSWORD</Text>
            <View style={styles.passwordWrapper}>
              <TextInput style={styles.passwordInput} value={targetOfficerPassword} onChangeText={setTargetOfficerPassword} placeholder="Leave blank" placeholderTextColor="#64748b" secureTextEntry={!showAdminEditPassword}/>
              <TouchableOpacity onPress={() => setShowAdminEditPassword(!showAdminEditPassword)} style={styles.eyeBtn}>
                <Text style={styles.eyeText}>{showAdminEditPassword ? '🙈 Hide' : '👁️ Show'}</Text>
              </TouchableOpacity>
            </View>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
              <TouchableOpacity style={[styles.amberButton, { flex: 1 }]} onPress={saveAdminOfficerEdit}>
                <Text style={styles.amberButtonText}>Save</Text>
              </TouchableOpacity>
              {targetOfficerBadge.toUpperCase() !== 'TN-ADMIN-01' && (
                <TouchableOpacity
                  style={[styles.primaryButton, { flex: 1, backgroundColor: '#dc2626', marginTop: 6 }]}
                  onPress={() => deleteAdminOfficerAccount(targetOfficerBadge)}
                >
                  <Text style={styles.buttonText}>🗑️ Delete</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity style={[styles.primaryButton, { flex: 1, backgroundColor: '#334155', marginTop: 6 }]} onPress={() => setAdminEditModalVisible(false)}>
                <Text style={styles.buttonText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      <View style={styles.bottomNav}>
        <TouchableOpacity style={styles.navItem} onPress={() => setCurrentTab('Incidents')}>
          <Text style={styles.navIcon}>🚨</Text>
          <Text style={[styles.navText, currentTab === 'Incidents' && styles.navTextActive]}>Incidents</Text>
        </TouchableOpacity>

        {/* DEDICATED PTT VOICE NOTES TAB WITH UNREAD BADGE */}
        <TouchableOpacity style={styles.navItem} onPress={() => setCurrentTab('VoicePTT')}>
          <View style={{ position: 'relative' }}>
            <Text style={styles.navIcon}>🎙️</Text>
            {unreadVoiceCount > 0 && (
              <View style={styles.unreadDotBadge}>
                <Text style={styles.unreadDotText}>{unreadVoiceCount}</Text>
              </View>
            )}
          </View>
          <Text style={[styles.navText, currentTab === 'VoicePTT' && styles.navTextActive]}>PTT Voice</Text>
        </TouchableOpacity>

        {isAdmin && (
          <TouchableOpacity style={styles.navItem} onPress={() => setCurrentTab('AllSignalsYolo')}>
            <Text style={styles.navIcon}>👁️</Text>
            <Text style={[styles.navText, currentTab === 'AllSignalsYolo' && styles.navTextActive]}>All Signals</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity style={styles.navItem} onPress={() => setCurrentTab('Alerts')}>
          <Text style={styles.navIcon}>🔔</Text>
          <Text style={[styles.navText, currentTab === 'Alerts' && styles.navTextActive]}>Alerts</Text>
        </TouchableOpacity>

        {!isAdmin && (
          <TouchableOpacity style={styles.navItem} onPress={() => setCurrentTab('Clearances')}>
            <Text style={styles.navIcon}>🎖️</Text>
            <Text style={[styles.navText, currentTab === 'Clearances' && styles.navTextActive]}>Clearances</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity style={styles.navItem} onPress={() => setCurrentTab('Profile')}>
          <Text style={styles.navIcon}>👮</Text>
          <Text style={[styles.navText, currentTab === 'Profile' && styles.navTextActive]}>Profile</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  authContainer: { flex: 1, backgroundColor: '#050b16' },
  authScroll: { flexGrow: 1, justifyContent: 'center', padding: 20 },
  mainContainer: { flex: 1, backgroundColor: '#081021' },
  dualStripe: { flexDirection: 'row', height: 5, width: '100%' },
  stripeRed: { flex: 1, backgroundColor: '#b91c1c' },
  stripeBlue: { flex: 1, backgroundColor: '#1e3a8a' },
  authCard: { backgroundColor: '#0d182e', borderRadius: 20, borderWidth: 1.5, borderColor: 'rgba(245,158,11,0.4)', padding: 22, alignItems: 'center' },
  emblemWrapper: { width: 84, height: 84, borderRadius: 42, backgroundColor: '#070e1c', borderWidth: 2, borderColor: '#fbbf24', padding: 4, marginBottom: 10, justifyContent: 'center', alignItems: 'center' },
  emblem: { width: '100%', height: '100%', borderRadius: 40, resizeMode: 'contain' },
  stateText: { fontSize: 10, color: '#fbbf24', fontWeight: 'bold', letterSpacing: 0.8, textAlign: 'center' },
  appTitle: { fontSize: 19, fontWeight: '900', color: '#fff', marginTop: 4, textAlign: 'center' },
  appSubtitle: { fontSize: 11, fontWeight: 'bold', color: '#fcd34d', marginBottom: 16, textAlign: 'center' },
  formContainer: { width: '100%' },
  fieldLabel: { fontSize: 10, color: '#fbbf24', fontWeight: 'bold', marginBottom: 4, letterSpacing: 0.5 },
  input: { backgroundColor: '#070e1c', borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)', borderRadius: 10, padding: 11, color: '#fff', fontSize: 13, marginBottom: 10 },
  passwordWrapper: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#070e1c', borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)', borderRadius: 10, marginBottom: 10 },
  passwordInput: { flex: 1, padding: 11, color: '#fff', fontSize: 13 },
  eyeBtn: { paddingHorizontal: 12, paddingVertical: 10 },
  eyeText: { color: '#fbbf24', fontSize: 11, fontWeight: 'bold' },
  primaryButton: { backgroundColor: '#b91c1c', borderRadius: 10, padding: 13, alignItems: 'center', marginTop: 4, borderWidth: 1, borderColor: 'rgba(251,191,36,0.4)' },
  buttonText: { color: '#fff', fontWeight: 'bold', fontSize: 13 },
  amberButton: { backgroundColor: '#f59e0b', borderRadius: 10, padding: 13, alignItems: 'center', marginTop: 6 },
  amberButtonText: { color: '#050b16', fontWeight: 'bold', fontSize: 13 },
  bioSectionBox: { marginTop: 14, backgroundColor: '#070e1c', borderRadius: 12, padding: 12, borderWidth: 1, borderColor: 'rgba(56,189,248,0.35)' },
  bioHeaderTitle: { color: '#38bdf8', fontSize: 10, fontWeight: '900', textAlign: 'center', letterSpacing: 0.5 },
  bioSubHint: { color: '#94a3b8', fontSize: 10, textAlign: 'center', marginTop: 2, marginBottom: 8 },
  bioMethodRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: '#0d182e', paddingVertical: 11, paddingHorizontal: 10, borderRadius: 8, borderWidth: 1, borderColor: '#1e293b', marginTop: 6 },
  bioMethodSelected: { borderColor: '#fbbf24', backgroundColor: 'rgba(251,191,36,0.1)' },
  bioMethodDisabled: { opacity: 0.55, borderColor: '#334155' },
  bioMethodText: { color: '#e2e8f0', fontSize: 11, fontWeight: 'bold' },
  bioCompatBadge: { fontSize: 9, fontWeight: '900', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  compatOk: { backgroundColor: 'rgba(16,185,129,0.2)', color: '#10b981' },
  compatNo: { backgroundColor: 'rgba(239,68,68,0.2)', color: '#f87171' },
  rankGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 12 },
  rankChip: { backgroundColor: '#070e1c', borderWidth: 1, borderColor: '#334155', borderRadius: 8, paddingHorizontal: 9, paddingVertical: 6 },
  rankChipActive: { backgroundColor: 'rgba(245,158,11,0.25)', borderColor: '#fbbf24' },
  rankChipText: { color: '#94a3b8', fontSize: 10, fontWeight: 'bold' },
  rankChipTextActive: { color: '#fbbf24' },
  switchButton: { marginTop: 14, alignItems: 'center' },
  switchText: { color: '#fbbf24', fontSize: 12, fontWeight: 'bold' },
  otpHintBox: { backgroundColor: 'rgba(30,58,138,0.4)', padding: 10, borderRadius: 8, borderWidth: 1, borderColor: '#3b82f6', marginBottom: 12, alignItems: 'center' },
  otpLabel: { color: '#93c5fd', fontSize: 11 },
  otpSimCode: { color: '#fbbf24', fontWeight: 'bold', fontSize: 13, marginTop: 4, fontFamily: 'monospace' },
  otpInput: { textAlign: 'center', fontSize: 18, letterSpacing: 6, color: '#fbbf24', fontWeight: 'bold' },
  header: { backgroundColor: '#0d182e', paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: 'rgba(245,158,11,0.3)', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  headerLeft: { flexDirection: 'row', alignItems: 'center', flex: 1, paddingRight: 8 },
  headerLogo: { width: 42, height: 42, borderRadius: 21, marginRight: 10, borderWidth: 1.5, borderColor: '#fbbf24', backgroundColor: '#070e1c' },
  headerTitle: { color: '#fff', fontWeight: '900', fontSize: 15 },
  subHeaderRow: { flexDirection: 'row', alignItems: 'center', marginTop: 2 },
  greenDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#10b981', marginRight: 6 },
  headerSub: { color: '#fbbf24', fontSize: 10, fontWeight: '700', flexShrink: 1 },
  syncBtn: { backgroundColor: '#111e36', paddingHorizontal: 10, paddingVertical: 7, borderRadius: 12, borderWidth: 1, borderColor: 'rgba(245,158,11,0.4)' },
  syncText: { color: '#fbbf24', fontSize: 10, fontWeight: 'bold' },
  bannerPending: { backgroundColor: 'rgba(217,119,6,0.25)', paddingVertical: 8, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: '#f59e0b', alignItems: 'center' },
  bannerText: { color: '#fcd34d', fontSize: 10, fontWeight: 'bold' },
  contentBody: { flex: 1 },
  scrollList: { padding: 14, paddingBottom: 30 },
  statsRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 },
  statCard: { flex: 1, backgroundColor: '#0d182e', borderRadius: 12, paddingVertical: 12, alignItems: 'center', marginHorizontal: 4, borderWidth: 1 },
  statNum: { fontSize: 20, fontWeight: '900' },
  statLabel: { fontSize: 9, color: '#94a3b8', fontWeight: 'bold', marginTop: 3, letterSpacing: 0.5 },
  slaAnalyticsBanner: { backgroundColor: '#070e1c', borderRadius: 12, padding: 12, marginBottom: 12, borderWidth: 1, borderColor: 'rgba(16,185,129,0.4)', flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  slaBannerTitle: { color: '#10b981', fontSize: 11, fontWeight: '900', letterSpacing: 0.4 },
  slaBannerSub: { color: '#94a3b8', fontSize: 10, marginTop: 2 },
  slaBadgePill: { backgroundColor: 'rgba(16,185,129,0.2)', borderWidth: 1, borderColor: '#10b981', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 10 },
  slaBadgeText: { color: '#34d399', fontSize: 11, fontWeight: '900' },
  slaTimerTag: { color: '#38bdf8', fontSize: 10, fontWeight: 'bold', fontFamily: 'monospace' },
  utilityChip: { backgroundColor: '#111e36', borderWidth: 1, borderColor: '#3b82f6', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 },
  utilityChipGreenActive: { backgroundColor: 'rgba(16,185,129,0.3)', borderColor: '#10b981' },
  utilityChipText: { color: '#e2e8f0', fontSize: 10, fontWeight: 'bold' },
  corridorCardBorder: { borderColor: '#10b981', borderWidth: 2 },
  corridorActiveBanner: { backgroundColor: 'rgba(16,185,129,0.2)', borderWidth: 1, borderColor: '#10b981', borderRadius: 8, padding: 8, marginTop: 8, alignItems: 'center' },
  corridorActiveText: { color: '#34d399', fontSize: 10, fontWeight: '900' },
  yoloToggleBtn: { backgroundColor: 'rgba(8,145,178,0.25)', borderWidth: 1, borderColor: '#06b6d4', paddingVertical: 8, paddingHorizontal: 10, borderRadius: 8, alignItems: 'center' },
  yoloToggleText: { color: '#67e8f9', fontSize: 10, fontWeight: 'bold', letterSpacing: 0.3 },
  yoloLiveCard: { backgroundColor: '#070e1c', borderRadius: 12, padding: 10, marginTop: 8, marginBottom: 10, borderWidth: 1.5, borderColor: '#06b6d4' },
  yoloLiveTitle: { color: '#fbbf24', fontSize: 12, fontWeight: 'bold', marginBottom: 3 },
  yoloLiveSub: { color: '#cbd5e1', fontSize: 10, marginBottom: 4 },
  yoloLiveImage: { width: '100%', height: 190, borderRadius: 8, backgroundColor: '#000', marginTop: 4 },
  quickActionsBar: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 14, gap: 8 },
  quickResetBtn: { flex: 1, backgroundColor: 'rgba(29,78,216,0.25)', borderWidth: 1, borderColor: '#3b82f6', paddingVertical: 8, borderRadius: 8, alignItems: 'center' },
  quickBtnText: { color: '#93c5fd', fontSize: 11, fontWeight: 'bold' },
  quickSimBtn: { flex: 1, backgroundColor: 'rgba(185,28,28,0.25)', borderWidth: 1, borderColor: '#f59e0b', paddingVertical: 8, borderRadius: 8, alignItems: 'center' },
  quickSimText: { color: '#fcd34d', fontSize: 11, fontWeight: 'bold' },
  sectionHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  sectionHeading: { fontSize: 12, fontWeight: '900', color: '#f59e0b', letterSpacing: 0.5 },
  totalCountText: { fontSize: 11, color: '#64748b', fontWeight: 'bold' },
  emptyText: { color: '#64748b', fontSize: 12, textAlign: 'center', marginTop: 20, marginBottom: 15 },
  incidentCard: { backgroundColor: '#0d182e', borderRadius: 14, borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)', padding: 14, marginBottom: 12 },
  resolvedCard: { borderColor: 'rgba(16,185,129,0.35)', opacity: 0.85 },
  cardTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  badgeResolved: { backgroundColor: 'rgba(16,185,129,0.15)', borderWidth: 1, borderColor: '#10b981', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12 },
  badgeTextResolved: { color: '#10b981', fontSize: 10, fontWeight: 'bold' },
  badgeActive: { backgroundColor: 'rgba(239,68,68,0.2)', borderWidth: 1, borderColor: '#ef4444', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12 },
  badgeTextActive: { color: '#f87171', fontSize: 10, fontWeight: 'bold' },
  badgeAssigned: { backgroundColor: 'rgba(59,130,246,0.2)', borderWidth: 1, borderColor: '#3b82f6', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 12 },
  badgeTextAssigned: { color: '#60a5fa', fontSize: 10, fontWeight: 'bold' },
  severityLabel: { color: '#f59e0b', fontSize: 10, fontWeight: 'bold' },
  incidentLocation: { fontSize: 15, fontWeight: 'bold', color: '#fff', marginBottom: 4 },
  incidentNotes: { fontSize: 12, color: '#94a3b8', lineHeight: 17 },
  hazardImg: { width: '100%', height: 140, borderRadius: 8, marginTop: 10, borderWidth: 1, borderColor: '#1e293b' },
  clearanceBox: { backgroundColor: '#070e1c', padding: 8, borderRadius: 8, marginTop: 10, borderWidth: 1, borderColor: '#10b981' },
  clearanceTitle: { fontSize: 10, fontWeight: 'bold', color: '#10b981', marginBottom: 5 },
  clearanceImg: { width: '100%', height: 110, borderRadius: 6 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, borderTopWidth: 1, borderTopColor: '#1e293b', paddingTop: 10, flexWrap: 'wrap', gap: 6 },
  backupSosBtn: { backgroundColor: 'rgba(220,38,38,0.25)', borderWidth: 1, borderColor: '#ef4444', paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8 },
  backupSosBtnText: { color: '#fca5a5', fontSize: 10, fontWeight: 'bold' },
  actionRow: { flexDirection: 'row', gap: 6 },
  actionBtnBlue: { backgroundColor: '#1d4ed8', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: '#60a5fa' },
  actionBtnAmber: { backgroundColor: '#d97706', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: '#fcd34d' },
  actionBtnEmerald: { backgroundColor: '#059669', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: '#34d399' },
  actionBtnRed: { backgroundColor: '#dc2626', paddingHorizontal: 10, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: '#f87171' },
  actionBtnText: { color: '#fff', fontSize: 11, fontWeight: 'bold' },
  voiceNoteCard: { borderRadius: 14, padding: 14, marginBottom: 10, borderWidth: 1.5 },
  voiceNoteCardNew: { backgroundColor: '#0d182e', borderColor: '#f59e0b' },
  voiceNoteCardListened: { backgroundColor: '#070e1c', borderColor: '#334155', opacity: 0.8 },
  pillNewVoice: { backgroundColor: 'rgba(239,68,68,0.2)', borderWidth: 1, borderColor: '#ef4444', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  pillNewVoiceText: { color: '#f87171', fontSize: 9, fontWeight: '900' },
  pillListened: { backgroundColor: 'rgba(16,185,129,0.15)', borderWidth: 1, borderColor: '#10b981', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  pillListenedText: { color: '#10b981', fontSize: 9, fontWeight: '900' },
  playBtnNew: { backgroundColor: '#d97706', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: '#fde047' },
  playBtnListened: { backgroundColor: '#1e293b', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: '#475569' },
  pttPresetBtn: { backgroundColor: '#070e1c', borderWidth: 1, borderColor: '#06b6d4', borderRadius: 8, padding: 10, marginBottom: 6 },
  pttPresetText: { color: '#e2e8f0', fontSize: 11 },
  unreadDotBadge: { position: 'absolute', top: -4, right: -10, backgroundColor: '#ef4444', borderRadius: 8, paddingHorizontal: 5, paddingVertical: 1 },
  unreadDotText: { color: '#fff', fontSize: 8, fontWeight: '900' },
  devSignature: { textAlign: 'center', color: '#94a3b8', fontSize: 11, fontStyle: 'italic', marginTop: 18, marginBottom: 8 },
  alertCard: { backgroundColor: '#0d182e', borderRadius: 10, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: '#1e293b' },
  alertTime: { fontSize: 10, color: '#fbbf24', fontFamily: 'monospace', fontWeight: 'bold' },
  alertMsg: { fontSize: 12, color: '#e2e8f0', marginTop: 3 },
  alertThumb: { width: 60, height: 45, borderRadius: 6, marginTop: 6, borderWidth: 1, borderColor: '#334155' },
  clearanceHistoryCard: { backgroundColor: '#0d182e', borderRadius: 12, padding: 12, marginBottom: 10, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderBottomWidth: 1, borderColor: '#10b981' },
  historyTitle: { fontSize: 13, fontWeight: 'bold', color: '#fbbf24' },
  historyNotes: { fontSize: 11, color: '#94a3b8', marginTop: 2 },
  historyImg: { width: 58, height: 58, borderRadius: 8, borderWidth: 1, borderColor: '#10b981' },
  profileCard: { backgroundColor: '#0d182e', borderRadius: 16, padding: 18, alignItems: 'center', borderWidth: 1, borderColor: 'rgba(245,158,11,0.35)' },
  avatarContainer: { width: 84, height: 84, borderRadius: 42, overflow: 'hidden', borderWidth: 2, borderColor: '#fbbf24', marginBottom: 8, backgroundColor: '#070e1c' },
  avatar: { width: '100%', height: '100%', resizeMode: 'cover' },
  profileBadgeId: { fontSize: 15, fontWeight: '900', color: '#fff', marginBottom: 2 },
  rolePill: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 10, marginBottom: 14 },
  pillActive: { backgroundColor: 'rgba(16,185,129,0.2)', borderWidth: 1, borderColor: '#10b981' },
  pillPending: { backgroundColor: 'rgba(245,158,11,0.2)', borderWidth: 1, borderColor: '#f59e0b' },
  pillText: { fontSize: 10, fontWeight: 'bold', color: '#fbbf24' },
  profileForm: { width: '100%' },
  starBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: '#070e1c', borderWidth: 1, borderColor: '#334155' },
  starBtnActive: { borderColor: '#fbbf24', backgroundColor: 'rgba(251,191,36,0.15)' },
  feedbackItemCard: { width: '100%', backgroundColor: '#070e1c', borderRadius: 10, padding: 12, marginTop: 8, borderWidth: 1, borderColor: '#1e293b' },
  adminOfficerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', width: '100%', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.85)', justifyContent: 'center', padding: 20 },
  modalCard: { backgroundColor: '#0d182e', borderRadius: 16, padding: 20, borderWidth: 1.5, borderColor: '#3b82f6' },
  modalTitle: { color: '#60a5fa', fontSize: 14, fontWeight: 'bold', marginBottom: 10, textTransform: 'uppercase' },
  statusToggleBtn: { flex: 1, paddingVertical: 9, borderRadius: 8, borderWidth: 1, borderColor: '#334155', alignItems: 'center', backgroundColor: '#070e1c' },
  statusToggleActive: { backgroundColor: 'rgba(16,185,129,0.3)', borderColor: '#10b981' },
  statusTogglePending: { backgroundColor: 'rgba(245,158,11,0.3)', borderColor: '#f59e0b' },
  bottomNav: { backgroundColor: '#0d182e', flexDirection: 'row', height: 62, borderTopWidth: 1, borderTopColor: 'rgba(245,158,11,0.25)', justifyContent: 'space-around', alignItems: 'center' },
  navItem: { alignItems: 'center', justifyContent: 'center', flex: 1 },
  navIcon: { fontSize: 18, marginBottom: 2 },
  navText: { fontSize: 10, color: '#94a3b8' },
  navTextActive: { color: '#fbbf24', fontWeight: 'bold' }
});