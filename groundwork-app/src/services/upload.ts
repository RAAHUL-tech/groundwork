import * as FileSystem from 'expo-file-system/legacy';
import { groundworkApi } from './api';

export interface UploadResult {
  jobId: string;
  roomScanId: string | null;
}

// Upload a local file URI directly to a presigned S3 PUT URL.
// expo-file-system handles the file:// → raw bytes conversion 
async function putToS3(uri: string, uploadUrl: string, _contentType: string) {
  const result = await FileSystem.uploadAsync(uploadUrl, uri, {
    httpMethod: 'PUT',
    uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
  });

  if (result.status < 200 || result.status >= 300) {
    throw new Error(`S3 upload failed (${result.status}): ${result.body}`);
  }
}

// ─── Single image/video (live camera) ────────────────────────────────────────

export async function uploadCameraPhoto(
  uri: string,
  contentType: string = 'image/jpeg',
  options?: { projectId?: string; roomLabel?: string; audioUri?: string }
): Promise<UploadResult> {
  const fileName = uri.split('/').pop() ?? 'photo.jpg';

  // 1. Get presigned PUT URL for image/video
  const presign = await groundworkApi.presign({
    file_name: fileName,
    content_type: contentType,
    project_id: options?.projectId,
    room_label: options?.roomLabel,
  });

  // 2. PUT image/video bytes directly to S3 (bypasses Flask server)
  await putToS3(uri, presign.upload_url, contentType);

  // 3. If there's a voice recording, upload it to S3 and pass the key to the worker
  let s3AudioKey: string | undefined;
  if (options?.audioUri) {
    const audioFileName = options.audioUri.split('/').pop() ?? 'voice.m4a';
    const audioExt = audioFileName.includes('.') ? audioFileName.split('.').pop() : 'm4a';
    const audioPresign = await groundworkApi.presign({
      file_name: audioFileName,
      content_type: `audio/${audioExt}`,
      room_scan_id: presign.room_scan_id ?? undefined,
    });
    await putToS3(options.audioUri, audioPresign.upload_url, `audio/${audioExt}`);
    s3AudioKey = audioPresign.s3_key;
  }

  // 4. Start vision pipeline → enqueues Celery task
  const job = await groundworkApi.startEstimate({
    s3_key: presign.s3_key,
    room_scan_id: presign.room_scan_id,
    project_id: options?.projectId,
    tier: 'standard',
    s3_audio_key: s3AudioKey,
  });

  return { jobId: job.job_id, roomScanId: presign.room_scan_id };
}

// ─── Multiple images (library picker) ────────────────────────────────────────

export interface LibraryAsset {
  uri: string;
  mimeType?: string | null;
  type?: string | null;
}

export async function uploadLibraryAssets(
  assets: LibraryAsset[],
  options?: { projectId?: string; roomLabel?: string; audioUri?: string }
): Promise<UploadResult> {
  if (assets.length === 0) {
    throw new Error('No assets to upload');
  }

  const allKeys: string[] = [];
  let roomScanId: string | null = null;

  // First asset creates the room_scan; remaining assets reuse it
  const first = assets[0];
  const firstContentType = resolveContentType(first);
  const firstPresign = await groundworkApi.presign({
    file_name: first.uri.split('/').pop() ?? 'file',
    content_type: firstContentType,
    project_id: options?.projectId,
    room_label: options?.roomLabel,
  });
  await putToS3(first.uri, firstPresign.upload_url, firstContentType);
  allKeys.push(firstPresign.s3_key);
  roomScanId = firstPresign.room_scan_id;

  const rest = assets.slice(1);
  const batches = chunk(rest, 5);
  for (const batch of batches) {
    const results = await Promise.all(
      batch.map(async (asset) => {
        const contentType = resolveContentType(asset);
        const presign = await groundworkApi.presign({
          file_name: asset.uri.split('/').pop() ?? 'file',
          content_type: contentType,
          project_id: options?.projectId,
          room_label: options?.roomLabel,
          room_scan_id: roomScanId ?? undefined,
        });
        await putToS3(asset.uri, presign.upload_url, contentType);
        return presign.s3_key;
      })
    );
    allKeys.push(...results);
  }

  // Upload audio to S3 if a voice recording was provided
  let s3AudioKey: string | undefined;
  if (options?.audioUri) {
    const audioFileName = options.audioUri.split('/').pop() ?? 'voice.m4a';
    const audioExt = audioFileName.includes('.') ? audioFileName.split('.').pop() : 'm4a';
    const audioPresign = await groundworkApi.presign({
      file_name: audioFileName,
      content_type: `audio/${audioExt}`,
      room_scan_id: roomScanId ?? undefined,
    });
    await putToS3(options.audioUri, audioPresign.upload_url, `audio/${audioExt}`);
    s3AudioKey = audioPresign.s3_key;
  }

  const job = await groundworkApi.startEstimate({
    s3_keys: allKeys,
    room_scan_id: roomScanId,
    project_id: options?.projectId,
    tier: 'standard',
    s3_audio_key: s3AudioKey,
  });

  return { jobId: job.job_id, roomScanId };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function resolveContentType(asset: LibraryAsset): string {
  if (asset.mimeType) return asset.mimeType;
  if (asset.type === 'video') return 'video/mp4';
  return 'image/jpeg';
}

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}
