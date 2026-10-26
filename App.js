import React, { useState, useEffect, useRef } from 'react';
import { 
  StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, 
  Image, Alert, ActivityIndicator, SafeAreaView, StatusBar, Vibration, Modal 
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

const API_BASE_URL = 'http://192.168.137.1:8000';

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [token, setToken] = useState('');
  const [currentTab, setCurrentTab] = useState('Incidents');
  const lastNotifIdRef = useRef(null);
  const locationSubscriptionRef = useRef(null);
  
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [isRegistering, setIsRegistering] = useState(false);
  
  const [regName, setRegName] = useState('');
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
  const [loading, setLoading] = useState(false);

  const [profileData, setProfileData] = useState({
    name: '', email: '', mobile: '', badge_number: '', profile_photo: null, status: 'ACTIVE'
  });
  const [editName, setEditName] = useState('');
  const [editMobile, setEditMobile] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editPassword, setEditPassword] = useState('');
  const [showProfilePassword, setShowProfilePassword] = useState(false);

  const [adminEditModalVisible, setAdminEditModalVisible] = useState(false);
  const [targetOfficerBadge, setTargetOfficerBadge] = useState('');
  const [targetOfficerName, setTargetOfficerName] = useState('');
  const [targetOfficerMobile, setTargetOfficerMobile] = useState('');
  const [targetOfficerEmail, setTargetOfficerEmail] = useState('');
  const [targetOfficerStatus, setTargetOfficerStatus] = useState('ACTIVE');
  const [targetOfficerPassword, setTargetOfficerPassword] = useState('');
  const [showAdminEditPassword, setShowAdminEditPassword] = useState(false);

  useEffect(() => {
    checkStoredToken();
    requestLocationPermissions();
    return () => {
      if (locationSubscriptionRef.current) {
        locationSubscriptionRef.current.remove();
      }
    };
  }, []);

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
    if (isLoggedIn && token) {
      fetchData();
      const interval = setInterval(fetchData, 2500);
      return () => clearInterval(interval);
    }
  }, [isLoggedIn, token]);

  useEffect(() => {
    const activeAssigned = blockades.find(b => b.status === 'ASSIGNED');
    if (activeAssigned && isLoggedIn) {
      startLiveLocationTracking(activeAssigned.id);
    } else {
      if (locationSubscriptionRef.current) {
        locationSubscriptionRef.current.remove();
        locationSubscriptionRef.current = null;
      }
    }
  }, [blockades, isLoggedIn]);

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

  const playPoliceTacticalSiren = (customMessage = 'Traffic blockade and road congestion detected.', isControlRoomAdmin = false) => {
    Vibration.vibrate([0, 500, 120, 500, 120, 800, 150, 900]);
    try {
      if (Speech && Speech.speak) {
        Speech.stop();
        const cleanText = customMessage.replace(/\[.*?\]/g, '').replace(/@/g, 'at');
        const voiceAnnouncement = isControlRoomAdmin
          ? `Attention Control Room! Police Emergency Alert! ${cleanText}`
          : `Attention Field Officer! Traffic Blockade and Congestion Alert! ${cleanText}. Proceed for immediate clearance.`;

        Speech.speak(voiceAnnouncement, { language: 'en-IN', pitch: 1.05, rate: 1.0 });
      }
    } catch (err) {
      console.log('Audio dispatch note:', err);
    }
  };

  const checkStoredToken = async () => {
    try {
      const savedToken = await AsyncStorage.getItem('token_8002');
      if (savedToken) { setToken(savedToken); setIsLoggedIn(true); }
    } catch (e) {}
  };

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
      setIsLoggedIn(true);
      setUsername(''); setPassword('');
    } catch (err) {
      Alert.alert('Login Failed', err.message || 'Incorrect Badge ID or Password.');
    } finally { setLoading(false); }
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
        body: JSON.stringify({ name: regName, email: regEmail, mobile: regMobile, badge_number: regBadge, password: regPassword })
      });
      if (!res.ok) throw new Error('Registration failed');
      Alert.alert('Registration Submitted', 'Officer account created! Awaiting admin approval.');
      setIsRegistering(false); setStepOtp(false); setUsername(regBadge);
    } catch (err) { Alert.alert('Registration Error', err.message); }
    finally { setLoading(false); }
  };

  const fetchData = async () => {
    try {
      const isControlAdmin = token.toUpperCase() === 'TN-ADMIN-01';
      const [blockRes, notifRes, profileRes, clearRes] = await Promise.all([
        fetch(`${API_BASE_URL}/blockades/`),
        fetch(`${API_BASE_URL}/notifications/`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API_BASE_URL}/api/profile`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API_BASE_URL}/api/my-clearances`, { headers: { 'Authorization': `Bearer ${token}` } })
      ]);

      if (blockRes.ok) setBlockades(await blockRes.json());
      if (notifRes.ok) {
        const nData = await notifRes.json();
        setNotifications(nData);
        if (nData.length > 0) {
          const newest = nData[nData.length - 1];
          if (lastNotifIdRef.current !== null && newest.id > lastNotifIdRef.current) {
            playPoliceTacticalSiren(newest.message, isControlAdmin);
            Alert.alert(
              isControlAdmin ? '🚨 CONTROL ROOM TACTICAL ALERT' : '🚨 BLOCKADE & CONGESTION ALERT',
              newest.message,
              [{ text: 'Acknowledge & View', onPress: () => setCurrentTab('Incidents') }]
            );
          }
          lastNotifIdRef.current = newest.id;
        }
      }
      if (profileRes.ok) {
        const prof = await profileRes.json();
        setProfileData(prof);
        if (!editName) setEditName(prof.name || '');
        if (!editMobile) setEditMobile(prof.mobile || '');
        if (!editEmail) setEditEmail(prof.email || '');
      }
      if (clearRes.ok) setMyClearances(await clearRes.json());

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

  const resetAllBlockades = async () => {
    if (token.toUpperCase() !== 'TN-ADMIN-01') return;
    try {
      await fetch(`${API_BASE_URL}/blockades/reset-all`, { method: 'POST', headers: { 'Authorization': `Bearer ${token}` } });
      fetchData(); Alert.alert('Database Reset');
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
        // DEMO OVERRIDE: Bypass geofence restriction for test account during presentation
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
                  `You are too far from the incident location (${distanceMeters.toFixed(0)}m away). You must be within 100 meters to mark arrived.`
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
          Alert.alert('Unit Dispatched 🚓', 'Live GPS telemetry stream active on Command Center Geo-Radar!');
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
      await fetch(`${API_BASE_URL}/blockades/${incident.id}/resolve-photo-base64`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_data: `data:image/jpeg;base64,${result.assets[0].base64}` })
      });
      fetchData();
    }
  };

  const saveProfileChanges = async () => {
    try {
      setLoading(true);
      const formData = new FormData();
      formData.append('name', editName);
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
          name: targetOfficerName, mobile: targetOfficerMobile, email: targetOfficerEmail,
          status: targetOfficerStatus, password: targetOfficerPassword.trim() !== '' ? targetOfficerPassword.trim() : null
        })
      });
      setAdminEditModalVisible(false); fetchData();
      Alert.alert('Success', 'Officer account updated.');
    } catch (e) { Alert.alert('Error'); }
  };

  const handleLogout = async () => {
    if (locationSubscriptionRef.current) {
      locationSubscriptionRef.current.remove();
      locationSubscriptionRef.current = null;
    }
    await AsyncStorage.removeItem('token_8002');
    setToken(''); setIsLoggedIn(false);
  };

  if (!isLoggedIn) {
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
                <TouchableOpacity style={styles.primaryButton} onPress={handleLogin}><Text style={styles.buttonText}>🛡️ Secure Login</Text></TouchableOpacity>
                <TouchableOpacity onPress={() => setIsRegistering(true)} style={styles.switchButton}>
                  <Text style={styles.switchText}>New Officer? Register Enrolment →</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <View style={styles.formContainer}>
                {!stepOtp ? (
                  <>
                    <Text style={styles.fieldLabel}>FULL NAME</Text>
                    <TextInput style={styles.input} placeholder="Inspector K. Murugan" placeholderTextColor="#64748b" value={regName} onChangeText={setRegName}/>
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
                      <Text style={styles.otpLabel}>OTP Dispatched</Text>
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

  const isAdmin = token.toUpperCase() === 'TN-ADMIN-01';
  const isPendingApproval = !isAdmin && profileData.status !== 'ACTIVE';
  const critCount = blockades.filter(b => b.severity === 'CRITICAL' && b.status !== 'RESOLVED').length;
  const dispCount = blockades.filter(b => b.status === 'ASSIGNED').length;
  const sceneCount = blockades.filter(b => b.status === 'ARRIVED').length;

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
              <Text style={styles.headerSub}>Command Center • {profileData.badge_number || token}</Text>
            </View>
          </View>
        </View>
        <TouchableOpacity style={styles.syncBtn} onPress={fetchData}><Text style={styles.syncText}>↻ SYNC</Text></TouchableOpacity>
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

            {isAdmin && (
              <View style={styles.quickActionsBar}>
                <TouchableOpacity style={styles.quickResetBtn} onPress={resetAllBlockades}><Text style={styles.quickBtnText}>🔄 Reset DB</Text></TouchableOpacity>
                <TouchableOpacity style={styles.quickSimBtn} onPress={simulateAIHazard}><Text style={styles.quickSimText}>📡 Simulate Hazard</Text></TouchableOpacity>
              </View>
            )}

            <View style={styles.sectionHeaderRow}>
              <Text style={styles.sectionHeading}>🚨 LIVE FIELD INCIDENTS & BLOCKADES</Text>
              <Text style={styles.totalCountText}>{blockades.length} TOTAL</Text>
            </View>

            {blockades.length === 0 ? (
              <Text style={styles.emptyText}>No active field blockades reported.</Text>
            ) : (
              blockades.slice().reverse().map(b => {
                const isResolved = b.status === 'RESOLVED';
                const statusBadgeStyle = isResolved ? styles.badgeResolved : b.status === 'ACTIVE' ? styles.badgeActive : styles.badgeAssigned;
                const statusTextStyle = isResolved ? styles.badgeTextResolved : b.status === 'ACTIVE' ? styles.badgeTextActive : styles.badgeTextAssigned;

                return (
                  <View key={b.id} style={[styles.incidentCard, isResolved && styles.resolvedCard]}>
                    <View style={styles.cardTopRow}>
                      <View style={statusBadgeStyle}><Text style={statusTextStyle}>• {b.status}</Text></View>
                      <Text style={styles.severityLabel}>SEVERITY: {b.severity}</Text>
                    </View>
                    <Text style={styles.incidentLocation}>📍 {b.location_name}</Text>
                    <Text style={styles.incidentNotes}>{b.notes}</Text>
                    {b.image_url ? <Image source={{ uri: b.image_url }} style={styles.hazardImg}/> : null}
                    {b.clearance_photo ? (
                      <View style={styles.clearanceBox}>
                        <Text style={styles.clearanceTitle}>📷 Clearance Verified ({b.resolved_by}):</Text>
                        <Image source={{ uri: b.clearance_photo }} style={styles.clearanceImg}/>
                      </View>
                    ) : null}

                    {!isResolved && !isAdmin && (
                      <View style={styles.cardFooter}>
                        <Text style={styles.telemetryHint}>
                          {b.status === 'ASSIGNED' ? '🛰️ Live GPS Telemetry Streaming...' : 'Awaiting Dispatch'}
                        </Text>
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

        {currentTab === 'Alerts' && (
          <ScrollView contentContainerStyle={styles.scrollList}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <Text style={styles.sectionHeading}>{isAdmin ? '🔔 MASTER TELEMETRY LOG' : '🚨 BLOCKADE ALERTS'}</Text>
              <TouchableOpacity onPress={() => playPoliceTacticalSiren('Test alert.', isAdmin)} style={{ backgroundColor: '#1e3a8a', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, borderWidth: 1, borderColor: '#fbbf24' }}>
                <Text style={{ color: '#fbbf24', fontSize: 10, fontWeight: 'bold' }}>🔊 Test Audio</Text>
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
            <Text style={styles.sectionHeading}>🎖️ MY PERSONAL LAST 10 CLEARANCES</Text>
            {myClearances.length === 0 ? (
              <Text style={styles.emptyText}>No clearances recorded.</Text>
            ) : (
              myClearances.map((c, index) => (
                <View key={c.id} style={styles.clearanceHistoryCard}>
                  <View style={{ flex: 1, paddingRight: 10 }}>
                    <Text style={styles.historyTitle}>#{index + 1} • {c.location_name}</Text>
                    <Text style={styles.historyNotes}>{c.notes}</Text>
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
              <View style={[styles.rolePill, profileData.status === 'ACTIVE' ? styles.pillActive : styles.pillPending]}>
                <Text style={styles.pillText}>STATUS: {profileData.status}</Text>
              </View>

              <View style={styles.profileForm}>
                <Text style={styles.fieldLabel}>FULL NAME</Text>
                <TextInput style={styles.input} value={editName} onChangeText={setEditName} placeholderTextColor="#64748b"/>
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
                  <Text style={styles.buttonText}>🚪 Logout</Text>
                </TouchableOpacity>
              </View>
            </View>

            {isAdmin && (
              <View style={[styles.profileCard, { marginTop: 16 }]}>
                <Text style={styles.sectionHeading}>🛡️ CENTRAL COMMAND: MANAGE OFFICERS</Text>
                {adminOfficers.map(off => (
                  <View key={off.id} style={styles.adminOfficerRow}>
                    <View style={{ flex: 1, paddingRight: 8 }}>
                      <Text style={{ color: '#fff', fontWeight: 'bold', fontSize: 12 }}>{off.name} ({off.badge_number})</Text>
                      <Text style={{ color: '#94a3b8', fontSize: 10 }}>{off.email} • {off.status}</Text>
                    </View>
                    <View style={{ flexDirection: 'row', gap: 6 }}>
                      {off.status === 'PENDING APPROVAL' && (
                        <TouchableOpacity style={styles.actionBtnEmerald} onPress={() => approveOfficerAccount(off.badge_number)}><Text style={styles.actionBtnText}>Approve</Text></TouchableOpacity>
                      )}
                      <TouchableOpacity style={styles.actionBtnBlue} onPress={() => openAdminEditOfficerModal(off)}><Text style={styles.actionBtnText}>✏️ Edit</Text></TouchableOpacity>
                    </View>
                  </View>
                ))}
              </View>
            )}
            <Text style={styles.devSignature}>Designed & Developed by Mohamed Hamdan</Text>
          </ScrollView>
        )}
      </View>

      <Modal visible={adminEditModalVisible} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>✏️ Edit Officer ({targetOfficerBadge})</Text>
            <Text style={styles.fieldLabel}>FULL NAME</Text>
            <TextInput style={styles.input} value={targetOfficerName} onChangeText={setTargetOfficerName}/>
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
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 8 }}>
              <TouchableOpacity style={[styles.amberButton, { flex: 1 }]} onPress={saveAdminOfficerEdit}><Text style={styles.amberButtonText}>Save</Text></TouchableOpacity>
              <TouchableOpacity style={[styles.primaryButton, { flex: 1, backgroundColor: '#334155' }]} onPress={() => setAdminEditModalVisible(false)}><Text style={styles.buttonText}>Cancel</Text></TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      <View style={styles.bottomNav}>
        <TouchableOpacity style={styles.navItem} onPress={() => setCurrentTab('Incidents')}><Text style={styles.navIcon}>🚨</Text><Text style={[styles.navText, currentTab === 'Incidents' && styles.navTextActive]}>Incidents</Text></TouchableOpacity>
        <TouchableOpacity style={styles.navItem} onPress={() => setCurrentTab('Alerts')}><Text style={styles.navIcon}>🔔</Text><Text style={[styles.navText, currentTab === 'Alerts' && styles.navTextActive]}>Alerts</Text></TouchableOpacity>
        {!isAdmin && (<TouchableOpacity style={styles.navItem} onPress={() => setCurrentTab('Clearances')}><Text style={styles.navIcon}>🎖️</Text><Text style={[styles.navText, currentTab === 'Clearances' && styles.navTextActive]}>Clearances</Text></TouchableOpacity>)}
        <TouchableOpacity style={styles.navItem} onPress={() => setCurrentTab('Profile')}><Text style={styles.navIcon}>👮</Text><Text style={[styles.navText, currentTab === 'Profile' && styles.navTextActive]}>Profile</Text></TouchableOpacity>
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
  authCard: { backgroundColor: '#0d182e', borderRadius: 20, borderWidth: 1.5, borderColor: 'rgba(245,158,11,0.4)', padding: 24, alignItems: 'center' },
  emblemWrapper: { width: 90, height: 90, borderRadius: 45, backgroundColor: '#070e1c', borderWidth: 2, borderColor: '#fbbf24', padding: 4, marginBottom: 10, justifyContent: 'center', alignItems: 'center' },
  emblem: { width: '100%', height: '100%', borderRadius: 40, resizeMode: 'contain' },
  stateText: { fontSize: 10, color: '#fbbf24', fontWeight: 'bold', letterSpacing: 0.8, textAlign: 'center' },
  appTitle: { fontSize: 19, fontWeight: '900', color: '#fff', marginTop: 4, textAlign: 'center' },
  appSubtitle: { fontSize: 11, fontWeight: 'bold', color: '#fcd34d', marginBottom: 20 },
  formContainer: { width: '100%' },
  fieldLabel: { fontSize: 10, color: '#fbbf24', fontWeight: 'bold', marginBottom: 4, letterSpacing: 0.5 },
  input: { backgroundColor: '#070e1c', borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)', borderRadius: 10, padding: 12, color: '#fff', fontSize: 13, marginBottom: 12 },
  passwordWrapper: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#070e1c', borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)', borderRadius: 10, marginBottom: 12 },
  passwordInput: { flex: 1, padding: 12, color: '#fff', fontSize: 13 },
  eyeBtn: { paddingHorizontal: 12, paddingVertical: 10 },
  eyeText: { color: '#fbbf24', fontSize: 11, fontWeight: 'bold' },
  primaryButton: { backgroundColor: '#b91c1c', borderRadius: 10, padding: 14, alignItems: 'center', marginTop: 4, borderWidth: 1, borderColor: 'rgba(251,191,36,0.4)' },
  buttonText: { color: '#fff', fontWeight: 'bold', fontSize: 13 },
  amberButton: { backgroundColor: '#f59e0b', borderRadius: 10, padding: 13, alignItems: 'center', marginTop: 6 },
  amberButtonText: { color: '#050b16', fontWeight: 'bold', fontSize: 13 },
  switchButton: { marginTop: 16, alignItems: 'center' },
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
  syncBtn: { backgroundColor: '#111e36', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 14, borderWidth: 1, borderColor: 'rgba(245,158,11,0.4)' },
  syncText: { color: '#fbbf24', fontSize: 11, fontWeight: 'bold' },
  bannerPending: { backgroundColor: 'rgba(217,119,6,0.25)', paddingVertical: 8, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: '#f59e0b', alignItems: 'center' },
  bannerText: { color: '#fcd34d', fontSize: 10, fontWeight: 'bold' },
  contentBody: { flex: 1 },
  scrollList: { padding: 14, paddingBottom: 30 },
  statsRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 14 },
  statCard: { flex: 1, backgroundColor: '#0d182e', borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginHorizontal: 4, borderWidth: 1 },
  statNum: { fontSize: 22, fontWeight: '900' },
  statLabel: { fontSize: 9, color: '#94a3b8', fontWeight: 'bold', marginTop: 3, letterSpacing: 0.5 },
  quickActionsBar: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 14, gap: 8 },
  quickResetBtn: { flex: 1, backgroundColor: 'rgba(29,78,216,0.25)', borderWidth: 1, borderColor: '#3b82f6', paddingVertical: 8, borderRadius: 8, alignItems: 'center' },
  quickBtnText: { color: '#93c5fd', fontSize: 11, fontWeight: 'bold' },
  quickSimBtn: { flex: 1, backgroundColor: 'rgba(185,28,28,0.25)', borderWidth: 1, borderColor: '#f59e0b', paddingVertical: 8, borderRadius: 8, alignItems: 'center' },
  quickSimText: { color: '#fcd34d', fontSize: 11, fontWeight: 'bold' },
  sectionHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  sectionHeading: { fontSize: 12, fontWeight: '900', color: '#f59e0b', letterSpacing: 0.5 },
  totalCountText: { fontSize: 11, color: '#64748b', fontWeight: 'bold' },
  emptyText: { color: '#64748b', fontSize: 12, textAlign: 'center', marginTop: 25 },
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
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, borderTopWidth: 1, borderTopColor: '#1e293b', paddingTop: 10 },
  telemetryHint: { fontSize: 10, color: '#60a5fa', fontWeight: '600', flex: 1 },
  actionRow: { flexDirection: 'row' },
  actionBtnBlue: { backgroundColor: '#1d4ed8', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: '#60a5fa' },
  actionBtnAmber: { backgroundColor: '#d97706', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: '#fcd34d' },
  actionBtnEmerald: { backgroundColor: '#059669', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1, borderColor: '#34d399' },
  actionBtnText: { color: '#fff', fontSize: 11, fontWeight: 'bold' },
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
  profileBadgeId: { fontSize: 15, fontWeight: '900', color: '#fff', marginBottom: 6 },
  rolePill: { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 10, marginBottom: 14 },
  pillActive: { backgroundColor: 'rgba(16,185,129,0.2)', borderWidth: 1, borderColor: '#10b981' },
  pillPending: { backgroundColor: 'rgba(245,158,11,0.2)', borderWidth: 1, borderColor: '#f59e0b' },
  pillText: { fontSize: 10, fontWeight: 'bold', color: '#fbbf24' },
  profileForm: { width: '100%' },
  adminOfficerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', width: '100%', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.85)', justifyContent: 'center', padding: 20 },
  modalCard: { backgroundColor: '#0d182e', borderRadius: 16, padding: 20, borderWidth: 1.5, borderColor: '#3b82f6' },
  modalTitle: { color: '#60a5fa', fontSize: 14, fontWeight: 'bold', marginBottom: 14, textTransform: 'uppercase' },
  statusToggleBtn: { flex: 1, paddingVertical: 9, borderRadius: 8, borderWidth: 1, borderColor: '#334155', alignItems: 'center', backgroundColor: '#070e1c' },
  statusToggleActive: { backgroundColor: 'rgba(16,185,129,0.3)', borderColor: '#10b981' },
  statusTogglePending: { backgroundColor: 'rgba(245,158,11,0.3)', borderColor: '#f59e0b' },
  bottomNav: { backgroundColor: '#0d182e', flexDirection: 'row', height: 62, borderTopWidth: 1, borderTopColor: 'rgba(245,158,11,0.25)', justifyContent: 'space-around', alignItems: 'center' },
  navItem: { alignItems: 'center', justifyContent: 'center', flex: 1 },
  navIcon: { fontSize: 18, marginBottom: 2 },
  navText: { fontSize: 10, color: '#94a3b8' },
  navTextActive: { color: '#fbbf24', fontWeight: 'bold' }
});