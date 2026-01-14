import React, { useEffect, useState, useRef, useMemo, Suspense } from 'react';
import { useGLTF } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import { useAppContext } from '../services/AppContext';
import ApiService from '../services/ApiService';
import { tfManager } from '../services/TFManager';
import * as THREE from 'three';

const RobotMesh = ({ url, rootFrame = 'base_footprint' }) => {
  // Append timestamp to URL to prevent caching issues if the URL is identical but content changed
  // (though backend usually generates unique URLs, it's safer)
  // But useGLTF might treat it as a new model and re-fetch.
  // We only want to re-fetch when the prop 'url' changes.
  // So we assume the parent component passes a fresh URL or we handle it there.
  
  const { scene, nodes } = useGLTF(url);

  // Debug: Log loaded nodes to help troubleshoot
  useEffect(() => {
    if (nodes) {
      // Optional: log details for a few nodes to see hierarchy
    }
  }, [nodes]);

  const groupRef = useRef();
  const frameIdCacheRef = useRef(new Map());
  
  // Clone the scene so we can have multiple instances if needed, and to avoid modifying the cached original
  const clonedScene = useMemo(() => scene.clone(), [scene]);
  const normalizeNodeName = (name) => {
    let n = String(name || '');
    n = n.replace(/_\d+$/, '');
    n = n.replace(/\.\d+$/, '');
    return n;
  };

  useFrame(() => {
    if (!groupRef.current) return;

    // 1. Update Root Position (Global Pose)
    const fixedFrame = tfManager.frames.has('map')
      ? 'map'
      : (tfManager.frames.has('odom') ? 'odom' : tfManager.getRootFrame());
    let resolvedRootFrame = rootFrame;
    if (!tfManager.frames.has(resolvedRootFrame)) {
      const suffix = `/${rootFrame}`;
      for (const fid of tfManager.frames.keys()) {
        if (fid.endsWith(suffix)) {
          resolvedRootFrame = fid;
          break;
        }
      }
    }
    const rootTransform = tfManager.getTransform(resolvedRootFrame, fixedFrame);
    if (rootTransform) {
      groupRef.current.position.set(rootTransform.position.x, rootTransform.position.y, rootTransform.position.z);
      groupRef.current.quaternion.set(rootTransform.quaternion.x, rootTransform.quaternion.y, rootTransform.quaternion.z, rootTransform.quaternion.w);
      groupRef.current.visible = true;
    }

    // 2. Update Articulated Links (Internal Joints)
    // Traverse the model and try to match child nodes with TF frames
    // Note: This relies on the GLB node names matching (or containing) the TF frame names.
    // Ideally, the baking process should preserve Link names from URDF.
    groupRef.current.traverse((child) => {
      // Skip the root group itself to avoid double transform
      if (child === groupRef.current) return;

      // Try to find a TF transform for this node
      // We look for a transform relative to the robot root (rootFrame)
      // Because the GLB structure usually has all parts relative to an origin, 
      // but in TF, parts are relative to their parents. 
      // HOWEVER, if we just move the meshes to their TF world pose relative to robot root, it works.
      
      // Heuristic: Check if node name exists in TF frames
      // GLTF names might be "link_1" or "link_1_Mesh"
      // We assume direct mapping for now.
      
      // Optimization: We can cache the mapping "NodeGUID -> FrameID" to avoid string search every frame
      // For now, simple lookup.
      
      let frameId = frameIdCacheRef.current.get(child.uuid);
      if (frameId === undefined) {
        const baseName = normalizeNodeName(child.name);
        if (tfManager.frames.has(baseName)) {
          frameId = baseName;
        } else {
          const suffix = `/${baseName}`;
          frameId = null;
          for (const fid of tfManager.frames.keys()) {
            if (fid.endsWith(suffix)) {
              frameId = fid;
              break;
            }
          }
        }
        frameIdCacheRef.current.set(child.uuid, frameId);
      }

      if (frameId) {
        const worldTransform = tfManager.getTransform(frameId, fixedFrame);
        
        if (worldTransform) {
          // Since the parent group (RobotModel) is already at 'base_footprint' (in Map),
          // we need the child's pose relative to 'base_footprint'.
          // T_base_to_child = inv(T_map_to_base) * T_map_to_child
          
          // BUT: useGLTF structure matters. 
          // If the GLB is "flat" (all meshes at root), we can just set their local position to T_base_to_child.
          // If the GLB is "hierarchical" (arm -> hand -> finger), modifying position breaks the chain unless we act carefully.
          
          // Safe approach for Visual Mesh (which is what we see):
          // Usually Visual Meshes are attached to Links.
          // If we can control the Link Node, we set its transform relative to Parent Link.
          // But TF gives us transform relative to Map (or we can ask relative to Parent).
          
          // SIMPLIFIED STRATEGY for flat-ish visual models:
          // We assume the GLB nodes represent Links.
          // We calculate T_root_to_link and apply it.
          // We need to convert the world transform (Map->Link) back to local space of the Group (Map->Root).
          
          // Let's use Three.js utilities for this relative calculation
          // Child World Pose = Map -> Link
          // Parent World Pose = Map -> Root
          
          // We want Local Pose s.t.: Parent World * Local = Child World
          // => Local = inv(Parent World) * Child World
          
          if (rootTransform) {
             const tMapRoot = new THREE.Matrix4().compose(
               new THREE.Vector3(rootTransform.position.x, rootTransform.position.y, rootTransform.position.z),
               new THREE.Quaternion(rootTransform.quaternion.x, rootTransform.quaternion.y, rootTransform.quaternion.z, rootTransform.quaternion.w),
               new THREE.Vector3(1,1,1)
             );
             
             const tMapLink = new THREE.Matrix4().compose(
               worldTransform.position,
               worldTransform.quaternion,
               new THREE.Vector3(1,1,1)
             );
             
             const tLocal = new THREE.Matrix4().copy(tMapRoot).invert().multiply(tMapLink);
             
             const pos = new THREE.Vector3();
             const quat = new THREE.Quaternion();
             const scale = new THREE.Vector3();
             tLocal.decompose(pos, quat, scale);
             
             child.position.copy(pos);
             child.quaternion.copy(quat);
             // Keep scale as is or reset? Usually keep.
          }
        }
      }
    });
  });

  return <primitive ref={groupRef} object={clonedScene} dispose={null} />;
};

const RobotModel = ({ robotType = 'turtlebot3' }) => {
  const { wsManager, addDebugInfo } = useAppContext();
  const [modelUrl, setModelUrl] = useState(null);
  const normalizeUrl = (raw) => {
    if (!raw) return null;
    let u = String(raw).trim();
    u = u.replace(/^[\s`"']+/, '').replace(/[\s`"']+$/, '');
    return u || null;
  };

  // 1. Fetch initial model
  useEffect(() => {
    let isMounted = true;
    const fetchModel = async () => {
      try {
        const model = await ApiService.fetchLatestRobotModel(robotType);
        if (!isMounted) return;
        
        if (model && model.display_model_url) {
          const cleanUrl = normalizeUrl(model.display_model_url);
          // [Fix] 将绝对 URL (http://10.144.144.2:9000/...) 转换为相对 URL (/tree-robot-assets/...)
          // 以利用 setupProxy.js 中的代理转发
          let proxyUrl = cleanUrl;
          if (cleanUrl) {
             if (cleanUrl.includes('/tree-robot-assets/')) {
                const pathIndex = cleanUrl.indexOf('/tree-robot-assets/');
                proxyUrl = cleanUrl.substring(pathIndex);
             } else if (cleanUrl.includes('10.144.144.2')) {
                // 如果 URL 中包含内网 IP 但没有 /tree-robot-assets/ 前缀（可能是直接 IP 访问）
                // 尝试强制替换，但这取决于 MinIO 的具体返回格式。
                // 现有的 setupProxy 只代理 /tree-robot-assets。
                // 假设 MinIO 返回的是 http://10.144.144.2:9000/bucket/... 
                // 我们需要确保路径匹配 setupProxy 的规则。
             }
          }
          setModelUrl(proxyUrl ? `${proxyUrl}?t=${Date.now()}` : null);
          addDebugInfo(`Loaded robot model: ${model.version}`, 'success');
        }
      } catch (err) {
        if (!isMounted) return;
        console.warn('[RobotModel] No active model found:', err);
        // Only log warning, do not set error state that might cause retry loop in parent if any
        addDebugInfo(`No active robot model found for ${robotType}`, 'warn');
      }
    };
    fetchModel();
    return () => { isMounted = false; };
  }, [robotType]);

  // 2. Listen for updates
  useEffect(() => {
    if (!wsManager) return;

    const handleUpdate = (msg) => {
      // Backend broadcasts: { type: "MODEL_UPDATED", payload: { robot_type, version, url } }
      // WebSocketManager emits: msg = { type:..., payload:... } (because msg.data is undefined)
      const data = msg.payload || msg.data || msg;
      
      // data: { robot_type, version, url }
      if (data && data.robot_type === robotType) {
        addDebugInfo(`Robot model updated: ${data.version}`, 'success');
        // Force a cache bust by appending time
        const cleanUrl = normalizeUrl(data.url);
        // [Fix] 将绝对 URL (http://10.144.144.2:9000/...) 转换为相对 URL (/tree-robot-assets/...)
        // 以利用 setupProxy.js 中的代理转发
        let proxyUrl = cleanUrl;
        if (cleanUrl) {
          if (cleanUrl.includes('/tree-robot-assets/')) {
            const pathIndex = cleanUrl.indexOf('/tree-robot-assets/');
            proxyUrl = cleanUrl.substring(pathIndex);
          } else if (cleanUrl.includes('10.144.144.2')) {
            // 如果 URL 中包含内网 IP 但没有 /tree-robot-assets/ 前缀（可能是直接 IP 访问）
            // 尝试强制替换，但这取决于 MinIO 的具体返回格式。
            // 现有的 setupProxy 只代理 /tree-robot-assets。
            // 假设 MinIO 返回的是 http://10.144.144.2:9000/bucket/... 
            // 我们需要确保路径匹配 setupProxy 的规则。
          }
        }
        setModelUrl(proxyUrl ? `${proxyUrl}?t=${Date.now()}` : null);
      }
    };

    // Assuming wsManager emits the event directly
    wsManager.on('MODEL_UPDATED', handleUpdate);

    return () => {
      wsManager.off('MODEL_UPDATED', handleUpdate);
    };
  }, [wsManager, robotType]);

  if (!modelUrl) return null;

  return (
    <group>
      <Suspense fallback={null}>
        <RobotMesh url={modelUrl} rootFrame="base_footprint" />
      </Suspense>
    </group>
  );
};

export default RobotModel;
