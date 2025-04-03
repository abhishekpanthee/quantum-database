"""
Statistical analysis tools for quantum database measurement results.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Union, Any
import scipy.stats as stats
import logging


class MeasurementStatistics:
    """
    Provides statistical analysis of quantum measurement results.
    """
    
    def __init__(self, confidence_level: float = 0.95):
        """
        Initialize the statistics analyzer.
        
        Args:
            confidence_level (float): Confidence level for statistical tests
        """
        self.confidence_level = confidence_level
        self.logger = logging.getLogger(__name__)
        
    def analyze_distribution(self, measurement_results: Dict) -> Dict:
        """
        Analyze the distribution of measurement results.
        
        Args:
            measurement_results (Dict): Results from quantum measurements
            
        Returns:
            Dict: Statistical analysis of the results
        """
        if "counts" not in measurement_results:
            self.logger.error("Invalid measurement results format")
            return {"error": "Invalid measurement results format"}
            
        counts = measurement_results["counts"]
        probabilities = measurement_results.get("probabilities", {})
        shots = measurement_results.get("shots", sum(counts.values()))
        
        # Calculate basic statistics
        entropy = self._calculate_entropy(probabilities)
        variance = self._calculate_variance(probabilities)
        
        # Calculate confidence intervals
        confidence_intervals = self._calculate_confidence_intervals(probabilities, shots)
        
        # Test for uniform distribution
        uniformity_test = self._test_uniformity(counts)
        
        # Determine if the distribution is likely a superposition
        is_superposition = self._detect_superposition(probabilities)
        
        # Analyze measurement quality
        quality_metrics = self._assess_measurement_quality(probabilities, shots)
        
        return {
            "entropy": entropy,
            "variance": variance,
            "confidence_intervals": confidence_intervals,
            "uniformity_test": uniformity_test,
            "superposition_detected": is_superposition,
            "measurement_quality": quality_metrics
        }
        
    def compare_distributions(self, distribution1: Dict, distribution2: Dict) -> Dict:
        """
        Compare two measurement distributions for statistical significance.
        
        Args:
            distribution1 (Dict): First measurement distribution
            distribution2 (Dict): Second measurement distribution
            
        Returns:
            Dict: Statistical comparison results
        """
        counts1 = distribution1.get("counts", {})
        counts2 = distribution2.get("counts", {})
        
        # Ensure both distributions cover the same bitstrings
        all_bitstrings = set(counts1.keys()) | set(counts2.keys())
        adjusted_counts1 = {bs: counts1.get(bs, 0) for bs in all_bitstrings}
        adjusted_counts2 = {bs: counts2.get(bs, 0) for bs in all_bitstrings}
        
        # Calculate statistical distance metrics
        kl_divergence = self._kl_divergence(distribution1.get("probabilities", {}),
                                           distribution2.get("probabilities", {}))
        
        # Chi-squared test for independence
        chi2_result = self._chi_squared_test(adjusted_counts1, adjusted_counts2)
        
        # Calculate total variation distance
        tvd = self._total_variation_distance(distribution1.get("probabilities", {}),
                                            distribution2.get("probabilities", {}))
        
        return {
            "kl_divergence": kl_divergence,
            "chi_squared_test": chi2_result,
            "total_variation_distance": tvd,
            "statistically_different": chi2_result["p_value"] < (1 - self.confidence_level)
        }
        
    def estimate_uncertainty(self, measurement_results: Dict) -> Dict:
        """
        Estimate the uncertainty in measurement results.
        
        Args:
            measurement_results (Dict): Results from quantum measurements
            
        Returns:
            Dict: Uncertainty estimates
        """
        probabilities = measurement_results.get("probabilities", {})
        shots = measurement_results.get("shots", 1000)
        
        # Standard errors for each outcome probability
        standard_errors = {}
        for bitstring, prob in probabilities.items():
            # Binomial standard error
            standard_errors[bitstring] = np.sqrt(prob * (1 - prob) / shots)
            
        # Overall uncertainty estimate
        mean_uncertainty = np.mean(list(standard_errors.values())) if standard_errors else 0
        max_uncertainty = max(standard_errors.values()) if standard_errors else 0
        
        # Calculate effective sample size considering correlation
        effective_sample_size = self._calculate_effective_sample_size(probabilities, shots)
        
        return {
            "standard_errors": standard_errors,
            "mean_uncertainty": mean_uncertainty,
            "max_uncertainty": max_uncertainty,
            "effective_sample_size": effective_sample_size,
            "shots": shots
        }
        
    def bootstrapped_statistics(self, measurement_results: Dict, n_bootstrap: int = 1000) -> Dict:
        """
        Perform bootstrap resampling to estimate statistics.
        
        Args:
            measurement_results (Dict): Results from quantum measurements
            n_bootstrap (int): Number of bootstrap samples
            
        Returns:
            Dict: Bootstrapped statistics
        """
        counts = measurement_results.get("counts", {})
        shots = measurement_results.get("shots", sum(counts.values()))
        
        # Convert counts to a list of measurement outcomes
        outcomes = []
        for bitstring, count in counts.items():
            outcomes.extend([bitstring] * count)
            
        # Initialize storage for bootstrap samples
        bootstrap_samples = []
        
        # Generate bootstrap samples
        for _ in range(n_bootstrap):
            # Resample with replacement
            sample = np.random.choice(outcomes, size=shots, replace=True)
            
            # Count occurrences
            sample_counts = {}
            for outcome in sample:
                sample_counts[outcome] = sample_counts.get(outcome, 0) + 1
                
            # Calculate probabilities
            sample_probs = {bs: count / shots for bs, count in sample_counts.items()}
            bootstrap_samples.append(sample_probs)
            
        # Calculate statistics on bootstrap samples
        bootstrap_stats = {
            "entropy": self._bootstrap_statistic(bootstrap_samples, self._calculate_entropy),
            "variance": self._bootstrap_statistic(bootstrap_samples, self._calculate_variance)
        }
        
        return bootstrap_stats
    
    def _calculate_entropy(self, probabilities: Dict) -> float:
        """
        Calculate the Shannon entropy of a probability distribution.
        
        Args:
            probabilities (Dict): Probability distribution
            
        Returns:
            float: Shannon entropy
        """
        entropy = 0.0
        for prob in probabilities.values():
            if prob > 0:  # Avoid log(0)
                entropy -= prob * np.log2(prob)
                
        return entropy
    
    def _calculate_variance(self, probabilities: Dict) -> float:
        """
        Calculate the variance of a probability distribution.
        
        Args:
            probabilities (Dict): Probability distribution
            
        Returns:
            float: Variance
        """
        # Convert bitstrings to integers for calculation
        values = [int(bs) if isinstance(bs, str) else bs for bs in probabilities.keys()]
        probs = list(probabilities.values())
        
        # Calculate mean
        mean = sum(v * p for v, p in zip(values, probs))
        
        # Calculate variance
        variance = sum((v - mean) ** 2 * p for v, p in zip(values, probs))
        
        return variance
    
    def _calculate_confidence_intervals(self, probabilities: Dict, shots: int) -> Dict:
        """
        Calculate confidence intervals for each probability.
        
        Args:
            probabilities (Dict): Probability distribution
            shots (int): Number of measurements
            
        Returns:
            Dict: Confidence intervals for each outcome
        """
        z = stats.norm.ppf((1 + self.confidence_level) / 2)
        intervals = {}
        
        for bitstring, prob in probabilities.items():
            # Standard error
            std_err = np.sqrt(prob * (1 - prob) / shots)
            
            # Confidence interval using normal approximation
            lower = max(0, prob - z * std_err)
            upper = min(1, prob + z * std_err)
            
            intervals[bitstring] = (lower, upper)
            
        return intervals
    
    def _test_uniformity(self, counts: Dict) -> Dict:
        """
        Test if the distribution is uniform.
        
        Args:
            counts (Dict): Count distribution
            
        Returns:
            Dict: Uniformity test results
        """
        # Chi-squared goodness-of-fit test
        values = list(counts.values())
        n = sum(values)
        k = len(values)
        
        if k <= 1:
            return {"is_uniform": True, "p_value": 1.0}
            
        # Expected count under uniform distribution
        expected = n / k
        
        # Chi-squared statistic
        chi2 = sum((obs - expected) ** 2 / expected for obs in values)
        
        # Degrees of freedom
        df = k - 1
        
        # P-value
        p_value = 1 - stats.chi2.cdf(chi2, df)
        
        return {
            "is_uniform": p_value > (1 - self.confidence_level),
            "p_value": p_value,
            "chi_squared": chi2,
            "degrees_of_freedom": df
        }
    
    def _detect_superposition(self, probabilities: Dict) -> bool:
        """
        Determine if the measurement likely came from a superposition state.
        
        Args:
            probabilities (Dict): Probability distribution
            
        Returns:
            bool: True if likely a superposition, False otherwise
        """
        # A superposition state typically has multiple outcomes with significant probability
        sig_outcomes = sum(1 for p in probabilities.values() if p > 0.05)
        
        # Also check the entropy - superpositions typically have higher entropy
        entropy = self._calculate_entropy(probabilities)
        max_entropy = np.log2(len(probabilities)) if probabilities else 0
        
        # Criteria for superposition detection
        return sig_outcomes > 1 and entropy > 0.5 * max_entropy
    
    def _assess_measurement_quality(self, probabilities: Dict, shots: int) -> Dict:
        """
        Assess the quality of quantum measurements.
        
        Args:
            probabilities (Dict): Probability distribution
            shots (int): Number of measurements
            
        Returns:
            Dict: Measurement quality metrics
        """
        # Calculate mean standard error
        std_errors = [np.sqrt(p * (1 - p) / shots) for p in probabilities.values()]
        mean_std_error = np.mean(std_errors) if std_errors else 0
        
        # Estimate sample size adequacy
        adequate_shots = shots >= 100 * len(probabilities)
        
        # Estimate if more shots would significantly improve precision
        marginal_improvement = 1 / np.sqrt(2 * shots) if shots > 0 else 0
        
        return {
            "mean_standard_error": mean_std_error,
            "adequate_sample_size": adequate_shots,
            "marginal_improvement": marginal_improvement,
            "recommended_shots": max(1000, 4 * shots) if mean_std_error > 0.01 else shots
        }
    
    def _kl_divergence(self, p: Dict, q: Dict) -> float:
        """
        Calculate Kullback-Leibler divergence between two distributions.
        
        Args:
            p (Dict): First probability distribution
            q (Dict): Second probability distribution
            
        Returns:
            float: KL divergence
        """
        # Ensure both distributions cover the same outcomes
        all_outcomes = set(p.keys()) | set(q.keys())
        
        # Calculate KL divergence
        kl = 0.0
        for outcome in all_outcomes:
            p_val = p.get(outcome, 0)
            q_val = q.get(outcome, 1e-10)  # Small value to avoid division by zero
            
            if p_val > 0:
                kl += p_val * np.log2(p_val / q_val)
                
        return kl
    
    def _chi_squared_test(self, counts1: Dict, counts2: Dict) -> Dict:
        """
        Perform chi-squared test for independence on two count distributions.
        
        Args:
            counts1 (Dict): First count distribution
            counts2 (Dict): Second count distribution
            
        Returns:
            Dict: Chi-squared test results
        """
        # Combine the counts into a contingency table
        outcomes = sorted(set(counts1.keys()) | set(counts2.keys()))
        
        # Create contingency table
        observed = np.array([
            [counts1.get(outcome, 0) for outcome in outcomes],
            [counts2.get(outcome, 0) for outcome in outcomes]
        ])
        
        # Perform chi-squared test
        chi2, p, dof, expected = stats.chi2_contingency(observed)
        
        return {
            "chi_squared": chi2,
            "p_value": p,
            "degrees_of_freedom": dof,
            "independent": p > (1 - self.confidence_level)
        }
    
    def _total_variation_distance(self, p: Dict, q: Dict) -> float:
        """
        Calculate total variation distance between two distributions.
        
        Args:
            p (Dict): First probability distribution
            q (Dict): Second probability distribution
            
        Returns:
            float: Total variation distance
        """
        # Ensure both distributions cover the same outcomes
        all_outcomes = set(p.keys()) | set(q.keys())
        
        # Calculate total variation distance (TVD)
        tvd = 0.5 * sum(abs(p.get(outcome, 0) - q.get(outcome, 0)) for outcome in all_outcomes)
        
        return tvd
    
    def _calculate_effective_sample_size(self, probabilities: Dict, shots: int) -> float:
        """
        Estimate the effective sample size considering correlation.
        
        Args:
            probabilities (Dict): Probability distribution
            shots (int): Number of measurements
            
        Returns:
            float: Effective sample size
        """
        # In quantum measurements, correlation can reduce effective sample size
        # This is a simplified model - in reality would use quantum-specific metrics
        
        # Calculate an estimate of correlation from the distribution shape
        entropy = self._calculate_entropy(probabilities)
        max_entropy = np.log2(len(probabilities)) if probabilities else 0
        
        if max_entropy == 0:
            return shots
            
        # Normalized entropy as a proxy for independence
        independence_factor = entropy / max_entropy
        
        # Calculate effective sample size
        effective_size = shots * independence_factor
        
        return effective_size
    
    def _bootstrap_statistic(self, bootstrap_samples: List[Dict], statistic_fn: callable) -> Dict:
        """
        Calculate statistics on bootstrap samples.
        
        Args:
            bootstrap_samples (List[Dict]): List of bootstrap probability distributions
            statistic_fn (callable): Function to calculate statistic
            
        Returns:
            Dict: Statistics on the bootstrap samples
        """
        # Calculate the statistic for each bootstrap sample
        statistics = [statistic_fn(sample) for sample in bootstrap_samples]
        
        # Calculate mean and standard deviation
        mean = np.mean(statistics)
        std_dev = np.std(statistics)
        
        # Calculate confidence interval
        alpha = 1 - self.confidence_level
        lower_percentile = alpha / 2 * 100
        upper_percentile = (1 - alpha / 2) * 100
        
        lower_bound = np.percentile(statistics, lower_percentile)
        upper_bound = np.percentile(statistics, upper_percentile)
        
        return {
            "mean": mean,
            "std_dev": std_dev,
            "confidence_interval": (lower_bound, upper_bound)
        }