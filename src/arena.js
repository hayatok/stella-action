import * as THREE from 'three';

export const RADIUS = 25;

export function addArena(scene) {
  scene.background = new THREE.Color(0xb77f91);
  scene.fog = new THREE.FogExp2(0xb77f91, 0.013);
  scene.add(new THREE.HemisphereLight(0xffe1ca, 0x646db4, 2.1));
  const sun = new THREE.DirectionalLight(0xffc79d, 2.5);
  sun.position.set(-15, 24, -12);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  Object.assign(sun.shadow.camera, { left: -28, right: 28, top: 28, bottom: -28, far: 75 });
  sun.shadow.normalBias = 0.04;
  scene.add(sun);

  const turf = new THREE.MeshStandardMaterial({ color: 0x6c8275, roughness: 0.95 });
  const earth = new THREE.MeshStandardMaterial({ color: 0x55445e, flatShading: true });
  const island = new THREE.Mesh(
    new THREE.CylinderGeometry(RADIUS, RADIUS * 0.9, 2, 64),
    [earth, turf, earth],
  );
  island.position.y = -1;
  island.receiveShadow = true;
  scene.add(island);
  const underside = new THREE.Mesh(new THREE.CylinderGeometry(22.5, 5, 10, 12), earth);
  underside.position.y = -7;
  scene.add(underside);

  const rockShape = new THREE.DodecahedronGeometry(1);
  const crystalShape = new THREE.OctahedronGeometry(1);
  const crystal = new THREE.MeshStandardMaterial({
    color: 0x89f1dc, emissive: 0x298d92, emissiveIntensity: 0.6, roughness: 0.35,
  });
  for (let i = 0; i < 24; i++) {
    const angle = i * Math.PI / 12;
    const radius = 22.5 + Math.sin(i * 8.1) * 1.1;
    const rock = new THREE.Mesh(rockShape, earth);
    rock.position.set(Math.sin(angle) * radius, 0.25, Math.cos(angle) * radius);
    rock.scale.set(0.7 + (i % 4) * 0.2, 0.55, 0.8);
    rock.rotation.y = i;
    rock.castShadow = true;
    scene.add(rock);
    if (i % 2 === 0) {
      const spire = new THREE.Mesh(crystalShape, crystal);
      spire.position.copy(rock.position).multiplyScalar(0.95);
      spire.position.y = 0.75;
      spire.scale.set(0.4, 1 + (i % 5) * 0.2, 0.4);
      spire.rotation.z = Math.sin(i) * 0.3;
      scene.add(spire);
    }
  }

  const sunDisc = new THREE.Mesh(
    new THREE.SphereGeometry(6, 24, 16),
    new THREE.MeshBasicMaterial({ color: 0xffc78d, fog: false }),
  );
  sunDisc.position.set(-40, 15, 75);
  scene.add(sunDisc);
}
