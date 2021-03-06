"""
Modular testing for core algorithms. For ease of testing each test makes use of parameterized fixtures defined in conftest.py. Fixtures are passed in as args to each test function which automatically generates a complete grid of parameter combinations for each test.

Tests are split up by model for ease of modular testing (i.e. using pytest -k 'test_name') and to avoid creating uneccesary parameter combinations, thereby reducing the total number of tests.

For running tests in parallel `pip install pytest-xdist` and for nicer testing output `pip install pytest-sugar`.

Then you can run pytest locally using `pytest -rs -n auto`, to see skip messages at the end of the test session and visually confirm that only intended skipped tests are being skipped. To aid in this, all pytest.skip() messages end with 'OK' for intentionally skipped tests.
"""

from emotioncf import Mean, KNN, NNMF_mult, NNMF_sgd, Base
import pytest
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def verify_fit(fit_kwargs):
    """Helper function to test fit call"""
    model = fit_kwargs.pop("model")
    model.fit(**fit_kwargs)
    assert model.is_fit
    assert model.predictions is not None
    return model.summary(), model


def verify_results(results, model, true_scores=None):
    """Helper function to test results object"""
    assert isinstance(results, pd.DataFrame)
    assert model.overall_results is not None
    assert model.user_results is not None
    assert model.user_results.shape == (model.data.shape[0], 4 * 3)
    # 4 metrics, 3 datasets, 2 "groups" (all, subject)
    assert results.shape == (4 * 3 * 2, 5)
    if model.is_dense:
        assert not results.isnull().any().any()
    else:
        assert results.isnull().sum().sum() == 8

    # For regression testing our results should be relatively consistent, this just ensures that. We expect performances to be in the same ballpark (+/- 2), so ignore MSE because that fluctuates much more than RMSE, MAE, or corr
    if true_scores is not None:
        assert np.allclose(
            results.query("metric != 'mse' and group == 'all'").score.to_numpy(),
            true_scores,
            atol=2,
        )


def verify_plotting(model):
    for dataset in ["full", "observed", "missing"]:
        out = model.plot_predictions(dataset=dataset)
        if dataset != "missing":
            assert isinstance(out, tuple)
        plt.close("all")


def test_downsample(simulate_wide_data):
    n_users, n_items = simulate_wide_data.shape
    cf = Base(simulate_wide_data)
    assert cf.data.shape == (n_users, n_items)

    # Test sampling_freq has no effect if target_type = 'samples'
    sampling_freq, target = 10, 2
    expected_items = int(n_items * (1 / target))
    cf.downsample(sampling_freq=sampling_freq, n_samples=target, target_type="samples")
    assert cf.data.shape == (n_users, expected_items)

    # Test each target_type
    sampling_freq, target = 10, 2
    cf = Base(simulate_wide_data)
    expected_items = int(n_items * (1 / (target * sampling_freq)))
    cf.downsample(sampling_freq=sampling_freq, n_samples=target, target_type="seconds")
    assert cf.data.shape == (n_users, expected_items)

    sampling_freq, target = 10, 5
    cf = Base(simulate_wide_data)
    expected_items = int(n_items * (1 / (sampling_freq / target)))
    cf.downsample(sampling_freq=sampling_freq, n_samples=target, target_type="hz")
    assert cf.data.shape == (n_users, expected_items)

    # Make sure downsampling affects fitted model artifacts
    cf = Mean(simulate_wide_data)
    cf.create_masked_data(n_mask_items=0.5)
    cf.fit()
    cf.downsample(sampling_freq=sampling_freq, n_samples=target, target_type="hz")
    assert cf.data.shape == (n_users, expected_items)
    assert cf.mask.shape == (n_users, expected_items)
    assert cf.masked_data.shape == (n_users, expected_items)
    assert cf.predictions.shape == (n_users, expected_items)

    # Make sure downsampling affects fitted model artifactsa including dilation
    cf = Mean(simulate_wide_data)
    cf.create_masked_data(n_mask_items=0.5)
    cf.fit(dilate_by_nsamples=5)
    cf.downsample(sampling_freq=sampling_freq, n_samples=target, target_type="hz")
    assert cf.data.shape == (n_users, expected_items)
    assert cf.mask.shape == (n_users, expected_items)
    assert cf.dilated_mask.shape == (n_users, expected_items)
    assert cf.masked_data.shape == (n_users, expected_items)
    assert cf.predictions.shape == (n_users, expected_items)


def test_init_and_dilate(init, mask, n_mask_items):
    """Test model initialization, initial masking, and dilation"""

    print(init.__class__.__name__)
    # Test that we calculate a mask
    if mask is not None or n_mask_items is not None:
        assert init.is_masked
        assert init.masked_data.isnull().any().any()

    # Test the mask is the right shape
    if n_mask_items is not None:
        total_items = init.data.shape[1]
        if isinstance(n_mask_items, (float, np.floating)):
            n_false_items = int(total_items * n_mask_items)
        else:
            n_false_items = n_mask_items
        calculated_n_false_items = init.masked_data.isnull().sum(1)[0]
        assert n_false_items == calculated_n_false_items

    # Test no accidental masking
    if mask is None and n_mask_items is None:
        assert not init.is_masked
        assert not init.masked_data.isnull().any().any()

        # Test fit failure when not masked
        with pytest.raises(ValueError):
            init.fit()
    if mask is not None or n_mask_items is not None:
        # Test dilation
        n_masked = init.masked_data.isnull().sum().sum()
        init.dilate_mask(n_samples=5)
        assert init.dilated_mask is not None
        assert init.is_mask_dilated is True
        # More values when we dilate the mask
        assert init.dilated_mask.sum().sum() > init.mask.sum().sum()
        # Fewer masked values after we dilate the mask
        assert n_masked > init.masked_data.isnull().sum().sum()


def test_mean(model, dilate_by_nsamples, n_mask_items):
    """Test Mean model"""
    if not isinstance(model, Mean):
        pytest.skip("Skip non Mean - OK")
    results, model = verify_fit(locals())
    if model.n_mask_items == 0.5 and not model.is_mask_dilated:
        true_scores = np.array(
            [
                8.12277126e-01,
                9.75982274e00,
                1.75006327e01,
                5.61000920e-01,
                1.95196455e01,
                2.47496320e01,
                1.00000000e00,
                0.00000000e00,
                0.00000000e00,
            ]
        )
    else:
        true_scores = None
    verify_results(results, model, true_scores)
    verify_plotting(model)


def test_knn(model, dilate_by_nsamples, n_mask_items, k, metric):
    """Test KNN model"""
    if not isinstance(model, KNN):
        pytest.skip("Skip non KNN - OK")
    results, model = verify_fit(locals())
    if model.n_mask_items == 0.5 and not model.is_mask_dilated and k == 3:
        true_scores = np.array(
            [
                0.91726067,
                7.25200471,
                12.36676527,
                0.84237887,
                14.50400943,
                17.48924716,
                1.0,
                0.0,
                0.0,
            ]
        )
    else:
        true_scores = None
    verify_results(results, model, true_scores)
    verify_plotting(model)


def test_nmf_mult(model, dilate_by_nsamples, n_mask_items, n_factors, n_iterations):
    """Test NNMF_mult model"""
    if not isinstance(model, NNMF_mult):
        pytest.skip("Skip non NNMF_mult - OK")
    results, model = verify_fit(locals())
    if (
        model.n_mask_items == 0.5
        and not model.is_mask_dilated
        and n_iterations == 100
        and n_factors is None
        and model.converged is True
    ):
        true_scores = np.array(
            [
                5.03636830e-01,
                1.89621113e01,
                3.39885854e01,
                -2.78597027e-02,
                3.69112079e01,
                4.80280757e01,
                9.97852743e-01,
                1.01301480e00,
                1.93696252e00,
            ]
        )
    else:
        true_scores = None
    verify_results(results, model, true_scores)
    verify_plotting(model)
    # Smoke test for plotting learning curves
    model.plot_learning()
    plt.close("all")


def test_nmf_sgd(model, dilate_by_nsamples, n_mask_items, n_factors, n_iterations):
    """Test NNMF_sgd model"""
    if not isinstance(model, NNMF_sgd):
        pytest.skip("Skip non NNMF_sgd - OK")
    results, model = verify_fit(locals())
    if (
        model.n_mask_items == 0.5
        and not model.is_mask_dilated
        and n_iterations == 100
        and n_factors is None
        and model.converged is True
    ):
        true_scores = np.array(
            [
                0.89757001,
                7.96887004,
                13.33854933,
                0.78658875,
                15.44602272,
                18.85269805,
                0.99977349,
                0.49171737,
                0.63997854,
            ]
        )
    else:
        true_scores = None
    verify_results(results, model, true_scores)
    verify_plotting(model)
    # Smoke test for plotting learning curves
    model.plot_learning()
    plt.close("all")
