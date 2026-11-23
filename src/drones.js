import * as THREE from 'three';
import { RADIUS } from './arena.js';

export function createDrones(scene) {
  const hull = new THREE.SphereGeometry(0.56, 16, 12);
  const ring = new THREE.TorusGeometry(0.62, 0.08, 8, 24);
  const eye = new THREE.SphereGeometry(0.19, 10, 8);
  const glow = new THREE.MeshStandardMaterial({ color: 0x8fffee, emissive: 0x2bc8c0 });
  const sparks = new THREE.IcosahedronGeometry(0.085, 0);
  const sparkColors = [0xffee9f, 0xffae75, 0x91ffe3].map(
    (color) => new THREE.MeshBasicMaterial({ color }),
  );
  const shardShape = new THREE.Shape();
  for (let i = 0; i < 10; i++) {
    const angle = i * Math.PI / 5 + Math.PI / 2;
    const radius = i % 2 === 0 ? 0.32 : 0.14;
    const x = Math.cos(angle) * radius;
    const y = Math.sin(angle) * radius;
    if (i === 0) shardShape.moveTo(x, y);
    else shardShape.lineTo(x, y);
  }
  shardShape.closePath();
  const shardGeometry = new THREE.ExtrudeGeometry(shardShape, { depth: 0.09, bevelEnabled: false });
  const shardMaterial = new THREE.MeshStandardMaterial({
    color: 0xffdc68, emissive: 0xffad32, emissiveIntensity: 0.7,
  });
  const particles = [];
  const shards = [];
  const drones = [[0, 5], [-5, 10], [6, 10]].map(([x, z], index) => {
    const group = new THREE.Group();
    const material = new THREE.MeshStandardMaterial({
      color: 0x524574, metalness: 0.35, roughness: 0.35,
    });
    const shell = new THREE.Mesh(hull, material);
    shell.scale.y = 0.68;
    shell.castShadow = true;
    const hoop = new THREE.Mesh(ring, glow);
    hoop.rotation.x = Math.PI / 2;
    const lens = new THREE.Mesh(eye, glow);
    lens.position.z = 0.49;
    group.add(shell, hoop, lens);
    scene.add(group);
    return { group, material, x, z, index, velocity: new THREE.Vector3(), hp: 3, flash: 0 };
  });

  function reset() {
    for (const { mesh } of [...particles, ...shards]) scene.remove(mesh);
    particles.length = 0;
    shards.length = 0;
    for (const drone of drones) {
      drone.group.position.set(drone.x, 0.95, drone.z);
      drone.group.visible = true;
      drone.hp = 3;
      drone.flash = 0;
      drone.velocity.set(0, 0, 0);
      drone.material.emissive.setHex(0);
    }
  }

  function burst(position, count) {
    for (let i = 0; i < count; i++) {
      const mesh = new THREE.Mesh(sparks, sparkColors[i % sparkColors.length]);
      mesh.position.copy(position);
      scene.add(mesh);
      const velocity = new THREE.Vector3(Math.random() - 0.5, Math.random(), Math.random() - 0.5)
        .multiplyScalar(count > 10 ? 9 : 5);
      particles.push({ mesh, velocity, life: 0.4 + Math.random() * 0.3 });
    }
  }

  const offset = new THREE.Vector3();
  const facing = new THREE.Vector3();
  function hit(position, yaw) {
    facing.set(Math.sin(yaw), 0, Math.cos(yaw));
    let hits = 0;
    for (const drone of drones) {
      if (drone.hp === 0) continue;
      offset.subVectors(drone.group.position, position);
      if (Math.abs(offset.y - 0.85) > 1.15) continue;
      offset.y = 0;
      if (offset.lengthSq() > 2.6 ** 2 || offset.normalize().dot(facing) < Math.cos(Math.PI / 3)) {
        continue;
      }
      hits++;
      drone.hp--;
      drone.flash = 0.22;
      drone.material.emissive.setHex(0xffffff);
      drone.velocity.copy(offset).multiplyScalar(2.1);
      const defeated = drone.hp === 0;
      burst(drone.group.position, defeated ? 24 : 8);
      if (defeated) {
        drone.group.visible = false;
        const mesh = new THREE.Mesh(shardGeometry, shardMaterial);
        mesh.position.copy(drone.group.position);
        scene.add(mesh);
        shards.push({ mesh, age: 0 });
      }
    }
    return hits;
  }

  function update(dt, elapsed, playerPosition) {
    for (const drone of drones) {
      if (drone.hp === 0) continue;
      const { group, velocity } = drone;
      group.position.addScaledVector(velocity, dt).clampLength(0, RADIUS - 1);
      velocity.multiplyScalar(Math.exp(-9 * dt));
      const homeX = drone.x - group.position.x;
      const homeZ = drone.z - group.position.z;
      const distanceFromHome = Math.hypot(homeX, homeZ);
      if (distanceFromHome > 0.5) {
        const fraction = Math.min(0.8 * dt, distanceFromHome - 0.5) / distanceFromHome;
        group.position.x += homeX * fraction;
        group.position.z += homeZ * fraction;
      }
      group.position.y = 0.95 + Math.sin(elapsed * 3 + drone.index) * 0.16;
      group.rotation.y = Math.atan2(playerPosition.x - group.position.x, playerPosition.z - group.position.z);
      drone.flash = Math.max(0, drone.flash - dt);
      drone.material.emissive.setHex(Math.ceil(drone.flash * 30) % 2 ? 0xffffff : 0);
    }
    for (let i = particles.length - 1; i >= 0; i--) {
      const particle = particles[i];
      particle.life -= dt;
      if (particle.life <= 0) {
        scene.remove(particle.mesh);
        particles.splice(i, 1);
        continue;
      }
      particle.velocity.y -= 8 * dt;
      particle.mesh.position.addScaledVector(particle.velocity, dt);
      particle.mesh.scale.setScalar(Math.min(1, particle.life * 5));
    }
    for (const shard of shards) {
      shard.age += dt;
      shard.mesh.rotation.y += dt * 2.7;
      shard.mesh.position.y = 0.45 + 0.5 * Math.exp(-5 * shard.age) + Math.sin(shard.age * 4) * 0.09;
    }
  }

  return { reset, hit, update, remaining: () => drones.filter((drone) => drone.hp > 0).length };
}
