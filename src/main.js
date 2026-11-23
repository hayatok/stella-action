import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { addArena, RADIUS } from './arena.js';
import { createDrones } from './drones.js';
import { createInput } from './input.js';
import { gradientMap } from './toon.js';
import './style.css';

const WALK_SPEED = 5;
const SWING_DURATION = 0.45;
const HIT_TIME = SWING_DURATION * 0.4;
const SLASH_POSE_TIME = 12 / 24;
const FADE = 0.12;
const states = ['Idle', 'Run', 'Jump', 'Attack'];

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 160);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.querySelector('#game').prepend(renderer.domElement);
addArena(scene);
const drones = createDrones(scene);

const player = new THREE.Group();
scene.add(player);
let mixer;
const actions = new Map();
let animation;
let characterState = 'Idle';

function animate(state, restart = false) {
  characterState = state;
  const next = actions.get(state);
  if (!next || (animation === next && !restart)) return;
  // Cancel any unfinished fade when quickly re-entering a state.
  if (animation && animation !== next) animation.fadeOut(FADE);
  next.reset().setEffectiveWeight(1).setEffectiveTimeScale(1).play();
  if (animation && animation !== next) next.fadeIn(FADE);
  animation = next;
}

new GLTFLoader().loadAsync(`${import.meta.env.BASE_URL}models/stella.glb`).then((gltf) => {
  mixer = new THREE.AnimationMixer(gltf.scene);
  for (const name of states) {
    let clip = THREE.AnimationClip.findByName(gltf.animations, name);
    if (!clip) continue;
    if (name === 'Jump') {
      clip = clip.clone();
      clip.tracks = clip.tracks.filter((track) => track.name !== 'Body.position');
    }
    const action = mixer.clipAction(clip);
    if (name === 'Jump' || name === 'Attack') {
      action.setLoop(THREE.LoopOnce, 1);
      action.clampWhenFinished = true;
    }
    actions.set(name, action);
  }
  const toonMaterials = new Map();
  function toToon(material) {
    if (!material.isMeshStandardMaterial) return material;
    if (!toonMaterials.has(material)) {
      toonMaterials.set(material, new THREE.MeshToonMaterial({
        gradientMap,
        map: material.map,
        color: material.color,
        emissive: material.emissive,
        emissiveMap: material.emissiveMap,
        emissiveIntensity: material.emissiveIntensity,
        transparent: material.transparent,
        opacity: material.opacity,
        side: material.side,
      }));
    }
    return toonMaterials.get(material);
  }
  gltf.scene.traverse((node) => {
    if (!node.isMesh) return;
    node.castShadow = true;
    node.material = Array.isArray(node.material)
      ? node.material.map(toToon)
      : toToon(node.material);
  });
  // Player movement and the authored model both face local +Z.
  player.add(gltf.scene);
  animate(characterState);
}).catch(() => {
  const dummy = new THREE.Mesh(
    new THREE.CapsuleGeometry(0.35, 0.9, 6, 12),
    new THREE.MeshStandardMaterial({ color: 0x51c5bc }),
  );
  dummy.position.y = 0.8;
  dummy.castShadow = true;
  player.add(dummy);
  document.querySelector('#fallback').hidden = false;
});

let yaw;
let orbitYaw;
let pitch;
let verticalSpeed;
let time;
let hitstop;
let clearDelay;
let cleared;
let swing;
const motion = new THREE.Vector3();
const cameraTarget = new THREE.Vector3();
const follow = new THREE.Vector3();
const cameraOffset = new THREE.Vector3();
const progress = document.querySelector('#progress');
const debugState = document.querySelector('#debug-state');
const clear = document.querySelector('#clear');
const restartButton = document.querySelector('#restart');

const input = createInput(renderer.domElement, (dx, dy) => {
  orbitYaw -= dx * 0.008;
  pitch = THREE.MathUtils.clamp(pitch + dy * 0.006, 0.16, 1.02);
}, () => {
  if (!cleared && !swing && player.position.y === 0) verticalSpeed = 8.5;
}, () => {
  if (cleared) return;
  if (!swing) {
    startSwing(1);
  } else if (swing.index < 3) {
    swing.queued = true;
  }
});

function startSwing(index) {
  swing = { index, age: 0, queued: false };
  animate('Attack', true);
}

function updateProgress() {
  progress.textContent = `ドローン ${3 - drones.remaining()} / 3 撃破`;
}

function reset() {
  player.position.set(0, 0, 0);
  player.rotation.y = 0;
  yaw = 0;
  orbitYaw = 0;
  pitch = 0.34;
  verticalSpeed = 0;
  time = 0;
  hitstop = 0;
  clearDelay = 0;
  cleared = false;
  swing = undefined;
  follow.set(0, 1.1, 0);
  mixer?.stopAllAction();
  animation = undefined;
  animate('Idle');
  drones.reset();
  updateProgress();
  clear.hidden = true;
  restartButton.blur();
}

restartButton.addEventListener('click', reset);
reset();

function updatePlayer(dt) {
  let speed = 0;
  if (swing) {
    const previousAge = swing.age;
    swing.age += dt;
    const stepTime = Math.min(swing.age, HIT_TIME) - Math.min(previousAge, HIT_TIME);
    motion.set(Math.sin(yaw), 0, Math.cos(yaw));
    player.position.addScaledVector(motion, stepTime * (0.35 / HIT_TIME));
    if (previousAge < HIT_TIME && swing.age >= HIT_TIME && drones.hit(player.position, yaw)) {
      hitstop = 0.06;
      updateProgress();
      if (drones.remaining() === 0) {
        cleared = true;
        clearDelay = 0.6;
      }
    }
    if (swing.age >= SWING_DURATION) {
      if (swing.queued && !cleared) startSwing(swing.index + 1);
      else swing = undefined;
    }
  } else if (!cleared) {
    const stick = input.movement();
    const sin = Math.sin(orbitYaw);
    const cos = Math.cos(orbitYaw);
    motion.set(sin * stick.y - cos * stick.x, 0, cos * stick.y + sin * stick.x);
    if (motion.lengthSq() > 0.0025) {
      yaw = Math.atan2(motion.x, motion.z);
      const moveSpeed = WALK_SPEED * (input.dashing() ? 1.6 : 1);
      speed = moveSpeed * motion.length();
      player.position.addScaledVector(motion, moveSpeed * dt);
    }
  }

  player.rotation.y = yaw;
  const edge = Math.hypot(player.position.x, player.position.z);
  if (edge > RADIUS - 0.45) {
    const scale = (RADIUS - 0.45) / edge;
    player.position.x *= scale;
    player.position.z *= scale;
  }
  if (verticalSpeed !== 0 || player.position.y > 0) {
    player.position.y = Math.max(0, player.position.y + verticalSpeed * dt);
    verticalSpeed = player.position.y > 0 ? verticalSpeed - 16 * dt : 0;
  }
  animate(swing ? 'Attack' : player.position.y > 0 ? 'Jump' : speed > 0 ? 'Run' : 'Idle');
  if (characterState === 'Run') animation?.setEffectiveTimeScale(speed / WALK_SPEED);
}

function updateAnimation(dt) {
  if (swing && animation && characterState === 'Attack') {
    // Match the authored slash pose to contact, then play the recovery.
    const age = Math.min(swing.age, SWING_DURATION);
    const duration = animation.getClip().duration;
    const poseTime = age <= HIT_TIME
      ? age * SLASH_POSE_TIME / HIT_TIME
      : SLASH_POSE_TIME + (duration - SLASH_POSE_TIME) * (age - HIT_TIME) / (SWING_DURATION - HIT_TIME);
    animation.setEffectiveTimeScale(Math.max(0, poseTime - animation.time) / dt);
  }
  mixer?.update(dt);
}

function updateCamera(dt) {
  cameraTarget.copy(player.position).addScaledVector(THREE.Object3D.DEFAULT_UP, 1.1);
  follow.lerp(cameraTarget, 1 - Math.exp(-11 * dt));
  const horizontal = Math.cos(pitch) * 5.6;
  cameraOffset.set(-Math.sin(orbitYaw) * horizontal, Math.sin(pitch) * 5.6, -Math.cos(orbitYaw) * horizontal);
  camera.position.copy(follow).add(cameraOffset);
  camera.lookAt(follow);
}

function resize() {
  renderer.setSize(window.innerWidth, window.innerHeight);
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();

let previousFrame;
renderer.setAnimationLoop((now) => {
  const elapsed = previousFrame === undefined ? 0 : Math.max(0, (now - previousFrame) / 1000);
  previousFrame = now;
  const frozen = Math.min(elapsed, hitstop);
  hitstop -= frozen;
  const dt = Math.min(elapsed - frozen, 0.05);
  if (dt > 0) {
    time += dt;
    updatePlayer(dt);
    updateAnimation(dt);
    drones.update(dt, time, player.position);
    if (clearDelay > 0) {
      clearDelay -= dt;
      if (clearDelay <= 0) {
        clear.hidden = false;
        restartButton.focus();
      }
    }
  }
  updateCamera(Math.min(elapsed, 0.05));
  const stateLabel = `STATE: ${characterState} / ${player.position.y > 0 ? 'AIR' : 'GROUND'}`;
  if (debugState.textContent !== stateLabel) debugState.textContent = stateLabel;
  renderer.render(scene, camera);
});
