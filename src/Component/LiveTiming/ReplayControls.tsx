import { FaPause, FaPlay, FaRedoAlt } from 'react-icons/fa'

type ReplayControlsProps = {
  isPlaying: boolean;
  currentIndex: number;
  totalSnapshots: number;
  onPlayPause: () => void;
  onSeek: (index: number) => void;
  formatTime: (seconds: number) => string;
}

function ReplayControls({
  isPlaying,
  currentIndex,
  totalSnapshots,
  onPlayPause,
  onSeek,
  formatTime
}: ReplayControlsProps) {

  const isAtEnd = currentIndex >= totalSnapshots - 1

  return (
    <div className="simple-replay-controls">
      <button
        className="simple-play-btn"
        onClick={onPlayPause}
        title={isAtEnd ? 'Restart' : isPlaying ? 'Pause' : 'Play'}
      >
        {isAtEnd ? <FaRedoAlt /> : isPlaying ? <FaPause /> : <FaPlay />}
      </button>

      <span className="simple-replay-time">
        {formatTime(currentIndex)} / {formatTime(totalSnapshots - 1)}
      </span>

      <input
        type="range"
        className="simple-replay-slider"
        min={0}
        max={totalSnapshots - 1}
        value={currentIndex}
        onChange={(e) => onSeek(Number(e.target.value))}
      />
    </div>
  )
}

export default ReplayControls
