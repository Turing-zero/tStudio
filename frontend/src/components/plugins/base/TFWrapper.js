import React, { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

/**
 * TFWrapper 组件
 * 负责将子组件（可视化内容）根据 TF (Transform) 信息进行定位和定向。
 * @param {object} props
 * @param {string} props.frameId - 目标 TF Frame 的 ID。
 * @param {import('../../../services/TFManager').TFManager} props.tfManager - TF 管理器实例。
 * @param {React.ReactNode} props.children - 需要被包裹和变换的 React 子组件。
 */
function TFWrapper({ frameId, tfManager, children }) {
  const groupRef = useRef();

  useFrame(() => {
    if (groupRef.current) {
      // 我们假设场景的固定参考系是 'world' 或 'map'，这里需要根据实际情况确定
      // 在此示例中，我们获取相对于场景根（即固定参考系）的变换
      const fixedFrame = tfManager.getRootFrame(); // 假设 tfManager 提供了获取根节点的方法
      const transform = tfManager.getTransform(frameId, fixedFrame);
      if (transform) {
        const { position, quaternion } = transform;
        groupRef.current.position.set(position.x, position.y, position.z);
        groupRef.current.quaternion.set(quaternion.x, quaternion.y, quaternion.z, quaternion.w);
        groupRef.current.visible = true;
      } else {
        // 如果找不到变换，不隐藏对象，而是将其放置在原点（保持与 ruoyi-ui 行为一致，方便调试）
        console.warn(`Transform from ${fixedFrame} to ${frameId} not found. Rendering at origin.`);
        groupRef.current.position.set(0, 0, 0);
        groupRef.current.quaternion.set(0, 0, 0, 1);
        groupRef.current.visible = true;
      }
    }
  });

  return <group ref={groupRef}>{children}</group>;
}

export default TFWrapper;
