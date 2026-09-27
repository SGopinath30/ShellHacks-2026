"use client";
import { OrbitControls } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { projectBounds } from "@/lib/geo";
import type { Project } from "@/lib/types";

export function SceneCamera({
  projects,
  resetSignal,
}: {
  projects: Project[];
  resetSignal: number;
}) {
  const { camera, size } = useThree();
  const controlsRef = useRef<OrbitControlsImpl | null>(null);
  const frame = useMemo(
    () => projectBounds(projects),
    [projects],
  );
  useEffect(() => {
    const centerX = frame?.centerX ?? 0,
      centerZ = frame?.centerZ ?? 0;
    const span = frame?.span ?? 180;
    const fov = (camera as { fov?: number }).fov ?? 42;
    const vertical = span / (2 * Math.tan((fov * Math.PI) / 360));
    const horizontal = vertical / Math.max(0.7, size.width / size.height);
    const distance = Math.max(vertical, horizontal) * 1.05;
    camera.position.set(
      centerX + distance * 0.6,
      distance * 0.85,
      centerZ + distance * 0.85,
    );
    camera.lookAt(centerX, 0, centerZ);
    camera.updateProjectionMatrix();
    controlsRef.current?.target.set(centerX, 0, centerZ);
    controlsRef.current?.update();
    // Reset is explicit; timeline changes do not move the user's camera.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera, resetSignal, frame?.centerX, frame?.centerZ, frame?.span]);
  return (
    <OrbitControls
      ref={controlsRef}
      enableRotate
      enablePan
      enableZoom
      enableDamping
      dampingFactor={0.08}
      minDistance={12}
      maxDistance={1800}
      maxPolarAngle={Math.PI / 2.1}
    />
  );
}
