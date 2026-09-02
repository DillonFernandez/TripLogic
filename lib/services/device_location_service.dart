import 'dart:async';

import 'package:geolocator/geolocator.dart';

enum LocationFailureReason {
  serviceDisabled,
  permissionDenied,
  permissionDeniedForever,
  timeout,
  unavailable,
}

class LocationServiceException implements Exception {
  const LocationServiceException(this.message, {required this.reason});

  final String message;
  final LocationFailureReason reason;

  bool get canOpenAppSettings {
    return reason == LocationFailureReason.permissionDeniedForever;
  }

  bool get canOpenLocationSettings {
    return reason == LocationFailureReason.serviceDisabled;
  }

  @override
  String toString() => message;
}

class DeviceLocationResult {
  const DeviceLocationResult({
    required this.latitude,
    required this.longitude,
    required this.accuracyMeters,
    required this.timestamp,
  });

  final double latitude;
  final double longitude;
  final double accuracyMeters;
  final DateTime timestamp;

  bool get isValid {
    return latitude.isFinite &&
        latitude >= -90 &&
        latitude <= 90 &&
        longitude.isFinite &&
        longitude >= -180 &&
        longitude <= 180;
  }
}

class DeviceLocationService {
  const DeviceLocationService();

  static const Duration _locationTimeout = Duration(seconds: 20);

  Future<DeviceLocationResult> getCurrentLocation() async {
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();

      if (!serviceEnabled) {
        throw const LocationServiceException(
          'Location services are disabled. '
          'Turn on device location and try again.',
          reason: LocationFailureReason.serviceDisabled,
        );
      }

      var permission = await Geolocator.checkPermission();

      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }

      if (permission == LocationPermission.denied) {
        throw const LocationServiceException(
          'Location permission was denied. '
          'Allow access to use your current location.',
          reason: LocationFailureReason.permissionDenied,
        );
      }

      if (permission == LocationPermission.deniedForever) {
        throw const LocationServiceException(
          'Location permission is permanently denied. '
          'Open the app settings and allow location access.',
          reason: LocationFailureReason.permissionDeniedForever,
        );
      }

      if (permission != LocationPermission.whileInUse &&
          permission != LocationPermission.always) {
        throw const LocationServiceException(
          'The device could not determine the '
          'location permission status.',
          reason: LocationFailureReason.unavailable,
        );
      }

      final locationSettings = LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: _locationTimeout,
      );

      final position = await Geolocator.getCurrentPosition(
        locationSettings: locationSettings,
      );

      final result = DeviceLocationResult(
        latitude: position.latitude,
        longitude: position.longitude,
        accuracyMeters: position.accuracy,
        timestamp: position.timestamp,
      );

      if (!result.isValid) {
        throw const LocationServiceException(
          'The device returned invalid location coordinates.',
          reason: LocationFailureReason.unavailable,
        );
      }

      return result;
    } on LocationServiceException {
      rethrow;
    } on LocationServiceDisabledException {
      throw const LocationServiceException(
        'Location services are disabled. '
        'Turn on device location and try again.',
        reason: LocationFailureReason.serviceDisabled,
      );
    } on PermissionDeniedException {
      throw const LocationServiceException(
        'Location permission was denied. '
        'Allow access to use your current location.',
        reason: LocationFailureReason.permissionDenied,
      );
    } on TimeoutException {
      throw const LocationServiceException(
        'The device took too long to find your location. '
        'Check your GPS signal and try again.',
        reason: LocationFailureReason.timeout,
      );
    } catch (_) {
      throw const LocationServiceException(
        'Your current location could not be retrieved.',
        reason: LocationFailureReason.unavailable,
      );
    }
  }

  Future<bool> openAppSettings() {
    return Geolocator.openAppSettings();
  }

  Future<bool> openLocationSettings() {
    return Geolocator.openLocationSettings();
  }
}
