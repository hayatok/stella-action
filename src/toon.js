import * as THREE from 'three';

export const gradientMap = new THREE.DataTexture(
  new Uint8Array([89, 140, 204, 255]), 4, 1, THREE.RedFormat,
);
gradientMap.minFilter = THREE.NearestFilter;
gradientMap.magFilter = THREE.NearestFilter;
gradientMap.colorSpace = THREE.NoColorSpace;
gradientMap.needsUpdate = true;
